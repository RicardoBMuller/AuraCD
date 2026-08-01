# Publicar o AuraCD no GitHub Pages

Este guia considera o usuário GitHub `ricardobmuller` e recomenda um repositório chamado `AuraCD`.

## 1. Criar o repositório

1. Entre no GitHub.
2. Clique em **New repository**.
3. Use o nome `AuraCD`.
4. Escolha **Public**.
5. Não marque a criação automática de README, `.gitignore` ou licença.
6. Clique em **Create repository**.

O endereço esperado será:

```text
https://github.com/ricardobmuller/AuraCD
```

## 2. Enviar o projeto pelo VS Code

Extraia o ZIP, abra a pasta `AuraCD_2_7_DISTRIBUICAO` no VS Code e execute no terminal:

```powershell
git init
git add .
git commit -m "Publica AuraCD 2.7"
git branch -M main
git remote add origin https://github.com/ricardobmuller/AuraCD.git
git push -u origin main
```

Caso o repositório já esteja conectado, use somente:

```powershell
git add .
git commit -m "Atualiza AuraCD"
git push
```

## 3. Ativar o GitHub Pages

1. No repositório, abra **Settings**.
2. No menu lateral, abra **Pages**.
3. Em **Build and deployment**, selecione **GitHub Actions**.
4. Volte à aba **Actions**.
5. Abra o workflow **Publicar site no GitHub Pages**.
6. Clique em **Run workflow** e confirme.

Depois de alguns minutos, o site deverá ficar disponível em:

```text
https://ricardobmuller.github.io/AuraCD/
```

O site está na pasta `docs`. Ele identifica automaticamente o usuário e o nome do repositório pela URL do GitHub Pages.

## 4. Gerar o instalador sem tela preta

1. Abra a aba **Actions**.
2. Selecione **Gerar instalador Windows**.
3. Clique em **Run workflow**.
4. Informe a versão, por exemplo `2.7.0`.
5. Clique no botão verde **Run workflow**.
6. Aguarde o workflow terminar com o indicador verde.

O GitHub fará automaticamente:

- instalação do Python;
- testes do projeto;
- empacotamento com PyInstaller em modo `windowed/noconsole`;
- criação do instalador gráfico com Inno Setup;
- geração do checksum SHA‑256;
- criação da Release `v2.7.0`;
- upload de `AuraCD-Setup.exe`.

## 5. Testar o download

Abra:

```text
https://ricardobmuller.github.io/AuraCD/
```

Clique em **Baixar AuraCD**. O botão aponta para:

```text
https://github.com/ricardobmuller/AuraCD/releases/latest/download/AuraCD-Setup.exe
```

Instale em um computador Windows e confirme:

- o instalador é gráfico;
- não aparece prompt de comando;
- o ícone é criado na área de trabalho;
- o atalho também aparece no menu Iniciar;
- o aplicativo inicia em janela própria;
- nenhuma tela preta permanece aberta durante a execução.

## 6. Publicar uma atualização

1. Altere os arquivos.
2. Envie as alterações:

```powershell
git add .
git commit -m "Atualiza o AuraCD"
git push
```

3. Na aba **Actions**, execute novamente **Gerar instalador Windows** com uma versão maior, como `2.7.1`.
4. O botão do site passará a baixar automaticamente a Release mais recente.

## Observação sobre o aviso do Windows

Sem assinatura digital, o Windows pode exibir um aviso de editor desconhecido ou do Microsoft Defender SmartScreen. Isso não é uma janela preta e não indica, por si só, que o arquivo esteja infectado; significa que o executável não possui uma assinatura de um editor verificado.

Para uma distribuição comercial e mais amigável a usuários leigos, configure a assinatura descrita em:

```text
GUIA_ASSINATURA_DIGITAL.md
```
