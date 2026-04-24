# Infrastructure Inventory

Coleta inventário completo de servidores Windows: hardware, sistema operacional, softwares instalados, serviços, usuários locais, interfaces de rede, compartilhamentos e hotfixes. Gera relatório HTML detalhado com tema dark.

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/Windows_Server-0078D6?style=flat&logo=windows&logoColor=white)
![PowerShell](https://img.shields.io/badge/PowerShell-5391FE?style=flat&logo=powershell&logoColor=white)

## O que coleta

| Categoria | Dados |
|-----------|-------|
| **Sistema** | OS, versão, build, uptime, último boot |
| **Hardware** | CPU (modelo, núcleos), RAM total |
| **Armazenamento** | Todas as partições com uso % |
| **Rede** | Interfaces, IPs, MAC, gateway, DNS, DHCP |
| **Software** | Todos os programas instalados (registro) |
| **Serviços** | Status e tipo de inicialização |
| **Usuários** | Contas locais, status e último logon |
| **Segurança** | Hotfixes recentes, compartilhamentos SMB |

## Uso

```bash
# Requer execução como Administrador para dados completos
python inventory.py
```

## Saída

Relatório HTML abre automaticamente no navegador:

```
inventory_SERVIDOR01_20260423_143022.html
```

## Requisitos

- Python 3.8+
- Windows Server 2016+ / Windows 10+
- Sem dependências externas (usa apenas stdlib + WMI nativo)
