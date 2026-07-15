# Assinatura digital opcional do AuraCD

O projeto funciona sem certificado, mas o Windows pode mostrar **Editor desconhecido** e o SmartScreen pode solicitar confirmação. Para distribuição pública ou comercial, o ideal é assinar `AuraCD.exe` e `AuraCD-Setup.exe` com um certificado de assinatura de código emitido para você ou sua empresa.

## Secrets esperados pelo workflow

O workflow já está preparado para dois Secrets:

```text
WINDOWS_CERTIFICATE_BASE64
WINDOWS_CERTIFICATE_PASSWORD
```

## Converter o certificado PFX para Base64

No PowerShell, execute:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\CAMINHO\certificado.pfx")) | Set-Clipboard
```

O conteúdo ficará na área de transferência.

## Cadastrar os Secrets

1. Abra o repositório no GitHub.
2. Entre em **Settings → Secrets and variables → Actions**.
3. Clique em **New repository secret**.
4. Crie `WINDOWS_CERTIFICATE_BASE64` e cole o conteúdo Base64.
5. Crie `WINDOWS_CERTIFICATE_PASSWORD` com a senha do PFX.

Na próxima execução do workflow, o GitHub usará o `SignTool` para assinar o aplicativo e o instalador com SHA‑256 e carimbo de data/hora.

Nunca envie o arquivo `.pfx` ao repositório e nunca coloque a senha em um arquivo do projeto.
