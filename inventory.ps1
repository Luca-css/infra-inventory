<#
.SYNOPSIS
    Infrastructure Inventory — levantamento completo de servidor Windows.
    Coleta 10 categorias de informações e gera relatório HTML com abas.
.NOTES
    Execute como Administrador para dados completos.
#>

#Requires -Version 5.1
$ErrorActionPreference = 'SilentlyContinue'

$hostname  = $env:COMPUTERNAME
$ts        = Get-Date -Format 'yyyyMMdd_HHmmss'
$geradoEm  = Get-Date -Format 'dd/MM/yyyy HH:mm:ss'
$saida     = Join-Path $PSScriptRoot "inventory_output"
if (-not (Test-Path $saida)) { New-Item -ItemType Directory -Path $saida | Out-Null }

Write-Host "`n  INFRASTRUCTURE INVENTORY" -ForegroundColor Cyan
Write-Host "  Host: $hostname | $geradoEm`n"

# ── 1. Sistema ────────────────────────────────────────────────────────────────
Write-Host "  [1/10] Sistema operacional..." -ForegroundColor Gray
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$sistema = [PSCustomObject]@{
    Hostname       = $hostname
    OS             = $os.Caption
    Versao         = $os.Version
    Build          = $os.BuildNumber
    Arquitetura    = $os.OSArchitecture
    Dominio        = $cs.Domain
    WorkGroup      = $cs.Workgroup
    UltimoBoot     = $os.LastBootUpTime.ToString('yyyy-MM-dd HH:mm:ss')
    Uptime         = "$([math]::Floor((New-TimeSpan $os.LastBootUpTime).TotalDays))d $([math]::Floor((New-TimeSpan $os.LastBootUpTime).Hours))h"
    TotalRAM_GB    = [math]::Round($cs.TotalPhysicalMemory/1GB, 1)
}

# ── 2. Hardware ───────────────────────────────────────────────────────────────
Write-Host "  [2/10] Hardware..." -ForegroundColor Gray
$bios = Get-CimInstance Win32_BIOS
$hw = [PSCustomObject]@{
    Fabricante   = $cs.Manufacturer
    Modelo       = $cs.Model
    NumeroSerie  = $bios.SerialNumber
    BIOS         = $bios.SMBIOSBIOSVersion
    BIOSData     = $bios.ReleaseDate.ToString('yyyy-MM-dd')
}

# ── 3. CPU ────────────────────────────────────────────────────────────────────
Write-Host "  [3/10] Processadores..." -ForegroundColor Gray
$cpus = Get-CimInstance Win32_Processor | ForEach-Object {
    [PSCustomObject]@{
        Nome      = $_.Name.Trim()
        Nucleos   = $_.NumberOfCores
        Threads   = $_.NumberOfLogicalProcessors
        Clock_MHz = $_.MaxClockSpeed
        Socket    = $_.SocketDesignation
        Carga     = "$($_.LoadPercentage)%"
    }
}

# ── 4. RAM ────────────────────────────────────────────────────────────────────
Write-Host "  [4/10] Memória RAM..." -ForegroundColor Gray
$ram = Get-CimInstance Win32_PhysicalMemory | ForEach-Object {
    [PSCustomObject]@{
        Slot        = $_.DeviceLocator
        Tamanho_GB  = [math]::Round($_.Capacity/1GB, 1)
        Velocidade  = "$($_.Speed) MHz"
        Tipo        = switch($_.MemoryType){20{'DDR';break}21{'DDR2';break}24{'DDR3';break}26{'DDR4';break}34{'DDR5';break}default{'N/A'}}
        Fabricante  = $_.Manufacturer
        PartNumber  = $_.PartNumber.Trim()
    }
}

# ── 5. Discos ─────────────────────────────────────────────────────────────────
Write-Host "  [5/10] Discos..." -ForegroundColor Gray
$discos = Get-PSDrive -PSProvider FileSystem | ForEach-Object {
    $total = $_.Used + $_.Free
    [PSCustomObject]@{
        Drive    = "$($_.Name):"
        Label    = $_.Description
        Usado_GB = [math]::Round($_.Used/1GB, 2)
        Livre_GB = [math]::Round($_.Free/1GB, 2)
        Total_GB = [math]::Round($total/1GB, 2)
        Uso_Pct  = if ($total -gt 0) { "$([math]::Round($_.Used/$total*100))%" } else { 'N/A' }
    }
}

# ── 6. Rede ───────────────────────────────────────────────────────────────────
Write-Host "  [6/10] Interfaces de rede..." -ForegroundColor Gray
$rede = Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object {
    $ips = Get-NetIPAddress -InterfaceIndex $_.InterfaceIndex -AddressFamily IPv4
    $gw  = (Get-NetRoute -InterfaceIndex $_.InterfaceIndex -DestinationPrefix '0.0.0.0/0').NextHop
    $dns = (Get-DnsClientServerAddress -InterfaceIndex $_.InterfaceIndex -AddressFamily IPv4).ServerAddresses
    [PSCustomObject]@{
        Interface  = $_.Name
        Descricao  = $_.InterfaceDescription
        MAC        = $_.MacAddress
        IP         = ($ips.IPAddress -join ', ')
        Gateway    = ($gw -join ', ')
        DNS        = ($dns -join ', ')
        Velocidade = "$([math]::Round($_.LinkSpeed/1MB)) Mbps"
    }
}

# ── 7. Software instalado ─────────────────────────────────────────────────────
Write-Host "  [7/10] Software instalado..." -ForegroundColor Gray
$regPaths = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$software = Get-ItemProperty $regPaths |
    Where-Object { $_.DisplayName -and $_.DisplayName -ne '' } |
    Select-Object DisplayName, DisplayVersion, Publisher,
        @{N='Instalado';E={$_.InstallDate}} |
    Sort-Object DisplayName | Select-Object -First 100

# ── 8. Serviços ───────────────────────────────────────────────────────────────
Write-Host "  [8/10] Serviços..." -ForegroundColor Gray
$servicos = Get-Service | Select-Object Name, DisplayName, Status,
    @{N='TipoInicio';E={(Get-CimInstance Win32_Service -Filter "Name='$($_.Name)'").StartMode}} |
    Sort-Object Status, Name

# ── 9. Usuários locais ────────────────────────────────────────────────────────
Write-Host "  [9/10] Usuários locais..." -ForegroundColor Gray
$usuarios = Get-LocalUser | ForEach-Object {
    $grupos = (Get-LocalGroup | Where-Object { (Get-LocalGroupMember $_ -EA 0).Name -contains "$hostname\$($_.Name)" }).Name
    [PSCustomObject]@{
        Nome          = $_.Name
        Habilitado    = $_.Enabled
        UltimoLogin   = if ($_.LastLogon) { $_.LastLogon.ToString('yyyy-MM-dd HH:mm') } else { 'Nunca' }
        SenhaExpira   = $_.PasswordExpires
        Grupos        = ($grupos -join ', ')
    }
}

# ── 10. Hotfixes ──────────────────────────────────────────────────────────────
Write-Host "  [10/10] Hotfixes..." -ForegroundColor Gray
$hotfixes = Get-HotFix | Select-Object HotFixID, Description,
    @{N='InstalledOn';E={$_.InstalledOn.ToString('yyyy-MM-dd')}} |
    Sort-Object InstalledOn -Descending

# ── HTML ──────────────────────────────────────────────────────────────────────
function Row($obj) {
    $props = $obj.PSObject.Properties
    ($props | ForEach-Object {
        $v = ($_.Value ?? '—').ToString(); if ($v.Length -gt 60) { $v = $v.Substring(0,60)+'…' }
        "<tr><th style='width:160px'>$($_.Name)</th><td>$([System.Web.HttpUtility]::HtmlEncode($v))</td></tr>"
    }) -join ''
}
function Table($dados, $campos) {
    if (-not $dados) { return "<p class='empty'>Sem dados.</p>" }
    $ths = ($campos | ForEach-Object { "<th>$_</th>" }) -join ''
    $rows = ($dados | Select-Object -First 150 | ForEach-Object {
        $o = $_; $tds = ($campos | ForEach-Object {
            $v = ($o.$_ ?? '—').ToString(); if($v.Length -gt 60){$v=$v.Substring(0,60)+'…'}
            "<td>$([System.Web.HttpUtility]::HtmlEncode($v))</td>"
        }) -join ''; "<tr>$tds</tr>"
    }) -join ''
    "<table><thead><tr>$ths</tr></thead><tbody>$rows</tbody></table>"
}

$tabs = @(
    @{id='sistema';  label='Sistema';   html="<table class='kv'>$(Row $sistema)</table>"}
    @{id='hw';       label='Hardware';  html="<table class='kv'>$(Row $hw)</table>"}
    @{id='cpu';      label='CPU';       html=$(Table $cpus @('Nome','Nucleos','Threads','Clock_MHz','Carga'))}
    @{id='ram';      label='RAM';       html=$(Table $ram @('Slot','Tamanho_GB','Velocidade','Tipo','Fabricante'))}
    @{id='discos';   label='Discos';    html=$(Table $discos @('Drive','Label','Usado_GB','Livre_GB','Total_GB','Uso_Pct'))}
    @{id='rede';     label='Rede';      html=$(Table $rede @('Interface','MAC','IP','Gateway','DNS','Velocidade'))}
    @{id='software'; label='Software';  html=$(Table $software @('DisplayName','DisplayVersion','Publisher'))}
    @{id='servicos'; label='Serviços';  html=$(Table $servicos @('Name','DisplayName','Status','TipoInicio'))}
    @{id='usuarios'; label='Usuários';  html=$(Table $usuarios @('Nome','Habilitado','UltimoLogin','Grupos'))}
    @{id='hotfixes'; label='Hotfixes';  html=$(Table $hotfixes @('HotFixID','Description','InstalledOn'))}
)

$tabButtons = ($tabs | ForEach-Object { "<button class='tab-btn' data-tab='$($_.id)'>$($_.label)</button>" }) -join ''
$tabPanels  = ($tabs | ForEach-Object { "<div class='tab-panel' id='$($_.id)'>$($_.html)</div>" }) -join ''

$html = @"
<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<title>Inventory — $hostname</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#020c1b;color:#c9d1d9}
header{background:#0a1628;border-bottom:1px solid #00d4ff22;padding:18px 32px}
header h1{font-size:1.2rem;color:#00d4ff}header p{color:#484f58;font-size:.82rem;margin-top:4px}
.tabs{display:flex;gap:4px;padding:16px 32px;flex-wrap:wrap;border-bottom:1px solid #ffffff08}
.tab-btn{background:#0a1628;border:1px solid #ffffff0a;color:#484f58;padding:7px 16px;
  border-radius:6px;cursor:pointer;font-size:.76rem;transition:.2s}
.tab-btn:hover{color:#c9d1d9;border-color:#ffffff22}
.tab-btn.active{background:#0d1f35;color:#00d4ff;border-color:#00d4ff44}
.tab-panel{display:none;padding:24px 32px}
.tab-panel.active{display:block}
table{width:100%;border-collapse:collapse;font-size:.76rem}
th{text-align:left;padding:7px 10px;color:#484f58;font-weight:500;border-bottom:1px solid #ffffff08}
td{padding:6px 10px;border-bottom:1px solid #ffffff05;font-family:monospace}
tr:hover td{background:#0d1f35}tr:last-child td{border:none}
table.kv th{width:180px;color:#00d4ff;background:#0a1628}
table.kv td{color:#c9d1d9}
.empty{color:#484f58;padding:20px;font-size:.82rem}
footer{text-align:center;padding:16px;color:#484f58;font-size:.72rem}
</style></head><body>
<header>
  <h1>Infrastructure Inventory</h1>
  <p>Host: <strong>$hostname</strong> &nbsp;·&nbsp; Gerado: $geradoEm</p>
</header>
<div class="tabs">$tabButtons</div>
$tabPanels
<footer>Infrastructure Inventory · PowerShell · $hostname · $geradoEm</footer>
<script>
const btns   = document.querySelectorAll('.tab-btn')
const panels = document.querySelectorAll('.tab-panel')
function show(id) {
  btns.forEach(b => b.classList.toggle('active', b.dataset.tab === id))
  panels.forEach(p => p.classList.toggle('active', p.id === id))
}
btns.forEach(b => b.addEventListener('click', () => show(b.dataset.tab)))
show('sistema')
</script>
</body></html>
"@

$htmlPath = Join-Path $saida "inventory_${hostname}_${ts}.html"
$html | Out-File $htmlPath -Encoding UTF8

Write-Host "`n  Relatório gerado: $htmlPath`n" -ForegroundColor Green
try { Start-Process $htmlPath } catch {}
