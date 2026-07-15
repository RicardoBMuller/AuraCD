# AuraCD 2.6 — distribuição para Windows e GitHub Pages

Player Hi‑Fi retrô para CDs de áudio, com identificação de discos, letras, informações do artista, reprodução contínua e acervo pessoal persistente.

## O que esta versão entrega

- Aplicativo Windows empacotado com Python e todas as dependências.
- Execução **sem terminal e sem janela preta**.
- Instalador gráfico em português.
- Instalação por usuário, normalmente sem solicitar senha de administrador.
- Ícone criado automaticamente na área de trabalho e no menu Iniciar.
- Interface aberta em janela própria por `pywebview`.
- Backend local executado silenciosamente no mesmo processo do aplicativo.
- Proteção contra duas instâncias abertas ao mesmo tempo.
- Site pronto para GitHub Pages na pasta `docs`.
- Workflow do GitHub Actions que gera o instalador em um computador Windows e publica uma Release.
- Download do site sempre apontando para `AuraCD-Setup.exe` da Release mais recente.
- Assinatura digital opcional por certificado PFX configurado nos Secrets do GitHub.

## Estrutura de distribuição

```text
AuraCD_2_6_DISTRIBUICAO/
├── .github/workflows/
│   ├── pages.yml                 # publica o site
│   └── release-windows.yml       # gera e publica o instalador
├── docs/                         # site do GitHub Pages
├── installer/AuraCD.iss          # instalador gráfico Inno Setup
├── packaging/                    # versão do executável e automação
├── static/ templates/ auracd/    # aplicativo
├── AuraCD.spec                   # PyInstaller sem console
├── GUIA_PUBLICACAO_GITHUB.md
└── GUIA_ASSINATURA_DIGITAL.md
```

## Experiência do usuário final

1. A pessoa acessa o site publicado no GitHub Pages.
2. Clica em **Baixar AuraCD**.
3. Executa `AuraCD-Setup.exe`.
4. Usa um instalador normal do Windows, sem prompt de comando.
5. O instalador cria o ícone **AuraCD** na área de trabalho.
6. Ao abrir o ícone, o aplicativo e o servidor local iniciam silenciosamente.
7. Ao fechar a janela do AuraCD, o servidor local também é encerrado.

O usuário final não precisa instalar Python, VS Code, Flask ou executar arquivos `.bat`.

## Publicação

Siga integralmente o arquivo:

```text
GUIA_PUBLICACAO_GITHUB.md
```

O processo recomendado é usar o GitHub Actions incluído. A compilação do executável precisa ocorrer no Windows; por isso o workflow usa um runner `windows-latest`.

## Desenvolvimento local

Os arquivos `.bat` existentes são destinados somente ao desenvolvimento. Eles podem abrir terminal porque exibem logs de instalação e diagnóstico. **Eles não são entregues ao usuário final pelo instalador.**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py --browser
```

Modo de demonstração:

```powershell
$env:AURACD_DEMO="1"
python app.py --browser
```

## Geração local do instalador

Em um Windows com Python 3.12 e Inno Setup 6:

```text
build_installer.bat
```

O resultado será:

```text
dist_installer\AuraCD-Setup.exe
```

O executável é produzido com `console=False`, portanto não cria janela de terminal durante a utilização normal.

## Dados do usuário

O acervo e as configurações permanecem fora da pasta instalada:

```text
%APPDATA%\AuraCD
```

Assim, a atualização ou desinstalação do programa não apaga automaticamente o acervo pessoal.
