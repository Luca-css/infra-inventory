"""
Infrastructure Inventory — coleta inventário completo de hardware, software,
serviços, usuários e rede de servidores Windows. Gera relatório HTML detalhado.
"""

import subprocess
import json
import os
import sys
import socket
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Inventario:
    hostname:    str = ""
    dominio:     str = ""
    os_nome:     str = ""
    os_versao:   str = ""
    os_build:    str = ""
    uptime:      str = ""
    ultimo_boot: str = ""
    cpu_modelo:  str = ""
    cpu_nucleos: int = 0
    cpu_logicos: int = 0
    ram_total_gb: float = 0.0
    discos:      List[dict] = field(default_factory=list)
    interfaces:  List[dict] = field(default_factory=list)
    softwares:   List[dict] = field(default_factory=list)
    servicos:    List[dict] = field(default_factory=list)
    usuarios:    List[dict] = field(default_factory=list)
    shares:      List[dict] = field(default_factory=list)
    hotfixes:    List[dict] = field(default_factory=list)


def _ps(script: str, timeout: int = 45) -> Optional[dict | list]:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout
        )
        raw = r.stdout.strip()
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def coletar() -> Inventario:
    inv = Inventario()

    print("  [1/8] Sistema operacional...")
    so = _ps("""
$os  = Get-WmiObject Win32_OperatingSystem
$cs  = Get-WmiObject Win32_ComputerSystem
$boot = $os.ConvertToDateTime($os.LastBootUpTime)
@{
    hostname    = $env:COMPUTERNAME
    dominio     = $cs.Domain
    os_nome     = $os.Caption
    os_versao   = $os.Version
    os_build    = $os.BuildNumber
    ultimo_boot = $boot.ToString('dd/MM/yyyy HH:mm:ss')
    uptime_dias = [math]::Round(((Get-Date) - $boot).TotalDays, 1)
} | ConvertTo-Json""")
    if so:
        inv.hostname    = so.get("hostname", "")
        inv.dominio     = so.get("dominio", "")
        inv.os_nome     = so.get("os_nome", "")
        inv.os_versao   = so.get("os_versao", "")
        inv.os_build    = so.get("os_build", "")
        inv.ultimo_boot = so.get("ultimo_boot", "")
        inv.uptime      = f"{so.get('uptime_dias', 0)} dias"

    print("  [2/8] CPU e memória...")
    hw = _ps("""
$cpu = Get-WmiObject Win32_Processor | Select-Object -First 1
$os  = Get-WmiObject Win32_OperatingSystem
@{
    cpu_modelo  = $cpu.Name.Trim()
    cpu_nucleos = $cpu.NumberOfCores
    cpu_logicos = $cpu.NumberOfLogicalProcessors
    ram_gb      = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
} | ConvertTo-Json""")
    if hw:
        inv.cpu_modelo   = hw.get("cpu_modelo", "")
        inv.cpu_nucleos  = int(hw.get("cpu_nucleos", 0))
        inv.cpu_logicos  = int(hw.get("cpu_logicos", 0))
        inv.ram_total_gb = float(hw.get("ram_gb", 0))

    print("  [3/8] Discos...")
    discos = _ps("""
Get-WmiObject Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
    @{
        letra    = $_.DeviceID
        label    = $_.VolumeName
        fs       = $_.FileSystem
        total_gb = [math]::Round($_.Size      / 1GB, 1)
        livre_gb = [math]::Round($_.FreeSpace / 1GB, 1)
        usado_pct= [math]::Round((1 - $_.FreeSpace/$_.Size)*100, 1)
    }
} | ConvertTo-Json -Depth 2""")
    if discos:
        inv.discos = discos if isinstance(discos, list) else [discos]

    print("  [4/8] Interfaces de rede...")
    net = _ps("""
Get-WmiObject Win32_NetworkAdapterConfiguration -Filter "IPEnabled=True" | ForEach-Object {
    @{
        descricao = $_.Description
        mac       = $_.MACAddress
        ips       = ($_.IPAddress -join ', ')
        gateway   = ($_.DefaultIPGateway -join ', ')
        dns       = ($_.DNSServerSearchOrder -join ', ')
        dhcp      = $_.DHCPEnabled
    }
} | ConvertTo-Json -Depth 2""")
    if net:
        inv.interfaces = net if isinstance(net, list) else [net]

    print("  [5/8] Softwares instalados...")
    sw = _ps("""
$paths = @(
    'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',
    'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'
)
Get-ItemProperty $paths -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName } |
    Select-Object DisplayName, DisplayVersion, Publisher, InstallDate |
    Sort-Object DisplayName |
    ConvertTo-Json -Depth 2""", timeout=60)
    if sw:
        inv.softwares = sw if isinstance(sw, list) else [sw]

    print("  [6/8] Serviços...")
    svcs = _ps("""
Get-Service | Select-Object Name, DisplayName, Status, StartType |
    Sort-Object Status, Name | ConvertTo-Json -Depth 2""")
    if svcs:
        inv.servicos = svcs if isinstance(svcs, list) else [svcs]

    print("  [7/8] Usuários locais...")
    users = _ps("""
Get-LocalUser | Select-Object Name, Enabled, LastLogon, Description, PasswordLastSet |
    ConvertTo-Json -Depth 2""")
    if users:
        inv.usuarios = users if isinstance(users, list) else [users]

    print("  [8/8] Compartilhamentos e hotfixes...")
    shares = _ps("Get-SmbShare | Select-Object Name, Path, Description | ConvertTo-Json -Depth 2")
    if shares:
        inv.shares = shares if isinstance(shares, list) else [shares]

    hotfixes = _ps("Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 20 HotFixID, Description, InstalledOn, InstalledBy | ConvertTo-Json -Depth 2")
    if hotfixes:
        inv.hotfixes = hotfixes if isinstance(hotfixes, list) else [hotfixes]

    return inv


def _tabela(colunas: list, linhas: list, vazia: str = "Nenhum registro.") -> str:
    if not linhas:
        return f'<p class="vazio">{vazia}</p>'
    ths = "".join(f"<th>{c}</th>" for c in colunas)
    trs = ""
    for linha in linhas:
        tds = "".join(f"<td>{v if v is not None else '—'}</td>" for v in linha)
        trs += f"<tr>{tds}</tr>"
    return f"<table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>"


def gerar_html(inv: Inventario, gerado_em: str) -> str:
    # Discos
    disk_rows = [(d["letra"], d.get("label") or "—", d.get("fs") or "—",
                  f'{d["total_gb"]} GB', f'{d["livre_gb"]} GB',
                  f'{d["usado_pct"]}%') for d in inv.discos]
    sec_disco = _tabela(["Drive","Label","FS","Total","Livre","Usado%"], disk_rows)

    # Rede
    net_rows = [(n.get("descricao","")[:40], n.get("mac",""), n.get("ips",""),
                 n.get("gateway",""), "Sim" if n.get("dhcp") else "Não") for n in inv.interfaces]
    sec_rede = _tabela(["Adaptador","MAC","IP(s)","Gateway","DHCP"], net_rows)

    # Software
    sw_rows = [(s.get("DisplayName","")[:50], s.get("DisplayVersion",""),
                s.get("Publisher","")[:30], s.get("InstallDate","")) for s in inv.softwares[:100]]
    sec_sw = _tabela(["Nome","Versão","Fabricante","Instalado"], sw_rows,
                     "Nenhum software encontrado.")

    # Serviços rodando
    svcs_running = [s for s in inv.servicos if str(s.get("Status","")) in ("4","Running")]
    svc_rows = [(s.get("Name",""), s.get("DisplayName","")[:40],
                 str(s.get("Status","")), str(s.get("StartType",""))) for s in svcs_running[:50]]
    sec_svc = _tabela(["Nome","Descrição","Status","Inicialização"], svc_rows)

    # Usuários
    usr_rows = [(u.get("Name",""), "Ativo" if u.get("Enabled") else "Inativo",
                 str(u.get("LastLogon",""))[:19], u.get("Description","")) for u in inv.usuarios]
    sec_usr = _tabela(["Usuário","Status","Último Logon","Descrição"], usr_rows)

    # Hotfixes
    hf_rows = [(h.get("HotFixID",""), h.get("Description",""),
                str(h.get("InstalledOn",""))[:10], h.get("InstalledBy","")) for h in inv.hotfixes]
    sec_hf = _tabela(["HotFix ID","Tipo","Instalado em","Por"], hf_rows)

    return f"""<!DOCTYPE html><html lang="pt-BR">
<head><meta charset="UTF-8"><title>Inventário — {inv.hostname}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',sans-serif;background:#020c1b;color:#c9d1d9}}
header{{background:linear-gradient(135deg,#020c1b,#0a2a4a);border-bottom:1px solid #00d4ff33;
        padding:22px 32px}}
header h1{{font-size:1.4rem;color:#00d4ff}}
header p{{opacity:.7;margin-top:4px;font-size:.85rem;color:#7ecfff}}
.container{{max-width:1200px;margin:24px auto;padding:0 16px}}
.resumo{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}}
.card{{background:#0a1628;border:1px solid #00d4ff22;border-radius:8px;padding:14px 18px}}
.card .label{{font-size:.72rem;color:#7ecfff;text-transform:uppercase;letter-spacing:.06em}}
.card .val{{font-size:1.05rem;font-weight:600;color:#e6edf3;margin-top:4px}}
section{{background:#0a1628;border:1px solid #00d4ff22;border-radius:10px;
         padding:18px 22px;margin-bottom:16px}}
section h3{{font-size:.85rem;text-transform:uppercase;letter-spacing:.08em;
            color:#00d4ff;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #00d4ff22}}
table{{width:100%;border-collapse:collapse;font-size:.8rem}}
th{{background:#0d1f38;text-align:left;padding:8px 10px;color:#7ecfff;font-weight:500}}
td{{padding:7px 10px;border-bottom:1px solid #ffffff08;color:#c9d1d9}}
tr:hover td{{background:#0d1f38}}
tr:last-child td{{border:none}}
.vazio{{color:#484f58;font-size:.83rem;padding:8px 0}}
footer{{text-align:center;padding:20px;color:#484f58;font-size:.75rem}}
</style></head>
<body>
<header>
  <h1>Inventário de Infraestrutura — {inv.hostname}</h1>
  <p>Domínio: <strong>{inv.dominio}</strong> &nbsp;|&nbsp;
     {inv.os_nome} {inv.os_versao} &nbsp;|&nbsp;
     Gerado: <strong>{gerado_em}</strong></p>
</header>
<div class="container">
  <div class="resumo">
    <div class="card"><div class="label">CPU</div><div class="val">{inv.cpu_modelo[:35]}</div></div>
    <div class="card"><div class="label">Núcleos / Threads</div><div class="val">{inv.cpu_nucleos} / {inv.cpu_logicos}</div></div>
    <div class="card"><div class="label">RAM Total</div><div class="val">{inv.ram_total_gb} GB</div></div>
    <div class="card"><div class="label">Uptime</div><div class="val">{inv.uptime}</div></div>
    <div class="card"><div class="label">Último Boot</div><div class="val">{inv.ultimo_boot}</div></div>
    <div class="card"><div class="label">Softwares</div><div class="val">{len(inv.softwares)}</div></div>
    <div class="card"><div class="label">Serviços Ativos</div><div class="val">{len([s for s in inv.servicos if str(s.get('Status','')) in ('4','Running')])}</div></div>
    <div class="card"><div class="label">Hotfixes (últ. 20)</div><div class="val">{len(inv.hotfixes)}</div></div>
  </div>
  <section><h3>Discos</h3>{sec_disco}</section>
  <section><h3>Interfaces de Rede</h3>{sec_rede}</section>
  <section><h3>Usuários Locais</h3>{sec_usr}</section>
  <section><h3>Serviços em Execução ({len(svcs_running)})</h3>{sec_svc}</section>
  <section><h3>Softwares Instalados ({len(inv.softwares)})</h3>{sec_sw}</section>
  <section><h3>Hotfixes Recentes</h3>{sec_hf}</section>
</div>
<footer>Infrastructure Inventory · github.com/Luca-css/infra-inventory · {gerado_em}</footer>
</body></html>"""


def main():
    print(f"\n  INFRASTRUCTURE INVENTORY")
    print(f"  Host: {socket.gethostname()}\n")

    inv       = coletar()
    gerado_em = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    saida     = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"inventory_{inv.hostname}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    )

    with open(saida, "w", encoding="utf-8") as f:
        f.write(gerar_html(inv, gerado_em))

    print(f"\n  Softwares encontrados: {len(inv.softwares)}")
    print(f"  Serviços em execução:  {len([s for s in inv.servicos if str(s.get('Status','')) in ('4','Running')])}")
    print(f"  Relatório: {saida}\n")

    try:
        os.startfile(saida)
    except Exception:
        pass


if __name__ == "__main__":
    if sys.platform != "win32":
        print("[AVISO] Este script foi feito para Windows.")
    main()
