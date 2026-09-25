# YouTube Downloader

Script em Python para baixar vídeos do YouTube (MP4 até 1080p) ou extrair
áudio em MP3, a partir de uma lista de URLs, de uma playlist ou de um único
vídeo.

## Recursos

- Baixa vídeo (MP4, até 1080p) ou áudio (MP3, 192kbps) com a mesma
  ferramenta.
- Três formas de informar o que baixar: arquivo de lista, playlist do
  YouTube ou uma única URL.
- Retry automático (3 tentativas, com espera crescente) em caso de falha.
- Histórico de URLs já baixadas, para nunca baixar a mesma coisa duas vezes.
- Barra de progresso no download e feedback durante a conversão do FFmpeg.
- Pastas de saída separadas para vídeo e áudio.
- Log detalhado de tudo em `log.txt`.

---

## 1. Requisitos

- **Python 3.9+**
- **FFmpeg**, instalado e com uma build completa (com o encoder
  `libmp3lame`, necessário para gerar MP3 — veja a seção
  [Problemas comuns](#problemas-comuns) se tiver dúvida sobre isso)
- As bibliotecas Python listadas em `requirements.txt`:
  - [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
  - [`tqdm`](https://github.com/tqdm/tqdm)

## 2. Instalação

### 2.1. Clonar o repositório

```bash
git clone <url-do-seu-repositorio>
cd <pasta-do-repositorio>
```

### 2.2. Instalar as dependências Python

```bash
pip install -r requirements.txt
```

Se preferir isolar num ambiente virtual:

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

pip install -r requirements.txt
```

### 2.3. Instalar o FFmpeg

O script **exige** o FFmpeg no sistema.

1. Baixe uma build **"full"** ou **"essentials"** em
   [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) (Windows).
   Essas builds já vêm com o encoder de MP3 (`libmp3lame`).
2. Extraia em uma pasta fixa, por exemplo `C:\ffmpeg\bin`.
3. Adicione essa pasta ao **PATH** do Windows (Painel de Controle →
   Variáveis de Ambiente), **ou** simplesmente informe o caminho toda vez
   que rodar o script com `--ffmpeg-location` (veja a seção de opções).

Para conferir se o FFmpeg está correto, rode no terminal:

```bash
ffmpeg -version
ffmpeg -encoders | findstr mp3      # Windows
ffmpeg -encoders | grep mp3         # Linux/Mac
```

Se `libmp3lame` não aparecer na segunda checagem, essa instalação do
FFmpeg não serve para gerar MP3 — troque por uma build completa.

---

## 3. Uso básico

Por padrão, o script lê `lista.txt` (uma URL por linha) e baixa cada uma
como vídeo MP4:

```bash
python baixar_v2.py
```

Para baixar áudio (MP3) em vez de vídeo, adicione `--mp3` em qualquer um
dos modos abaixo:

```bash
python baixar_v2.py --mp3
```

### 3.1. Arquivo `lista.txt`

- Uma URL por linha.
- Linhas em branco são ignoradas.
- Linhas começando com `#` são tratadas como comentário e ignoradas.
- Linhas que não começam com `http://` ou `https://` são ignoradas com
  aviso (evita erros por texto solto na lista).
- Se o arquivo não existir, o script cria um `lista.txt` vazio
  automaticamente na primeira execução.

Exemplo de `lista.txt`:

```text
# Aulas da faculdade
https://www.youtube.com/watch?v=aaaaaaaaaaa
https://www.youtube.com/watch?v=bbbbbbbbbbb

# Músicas
https://www.youtube.com/watch?v=ccccccccccc
```

Conforme cada URL é processada com sucesso, ela é **removida** de
`lista.txt` e **adicionada** a `url_historico.txt`. Se uma URL falhar
mesmo após as tentativas automáticas, ela **permanece** em `lista.txt`
para uma próxima execução.

---

## 4. Opções (linha de comando)

| Opção                    | Descrição                                                                                          |
|---------------------------|-----------------------------------------------------------------------------------------------------|
| `--mp3`                   | Baixa o melhor áudio disponível e converte para MP3 (192kbps). Sem essa flag, baixa vídeo MP4.      |
| `--url URL`               | Baixa **um único vídeo** a partir da URL informada. Não usa `lista.txt`.                            |
| `--playlist URL`          | Baixa **todos os vídeos de uma playlist** do YouTube. Não usa `lista.txt`.                          |
| `--list ARQUIVO`          | Usa um arquivo de lista **diferente** de `lista.txt` (mesmo formato).                                |
| `--ffmpeg-location PASTA` | Caminho da pasta `bin` de uma instalação específica do FFmpeg (útil se houver mais de uma no PATH). |

### Prioridade quando mais de uma fonte é passada

Se você combinar `--url`, `--playlist` e/ou `--list` no mesmo comando
(o que normalmente não faz sentido), o script segue esta ordem de
prioridade e avisa qual foi ignorado:

```
--url  >  --playlist  >  --list / lista.txt
```

---

## 5. Exemplos de uso

**Baixar tudo que está em `lista.txt`, como vídeo:**
```bash
python baixar_v2.py
```

**Baixar tudo que está em `lista.txt`, como MP3:**
```bash
python baixar_v2.py --mp3
```

**Usar um arquivo de lista diferente:**
```bash
python baixar_v2.py --list musicas_2026.txt --mp3
```

**Baixar uma playlist inteira em vídeo:**
```bash
python baixar_v2.py --playlist "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxxxxxxxx"
```

**Baixar o áudio de uma playlist inteira:**
```bash
python baixar_v2.py --playlist "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxxxxxxxx" --mp3
```

**Baixar um único vídeo específico:**
```bash
python baixar_v2.py --url "https://www.youtube.com/watch?v=xxxxxxxxxxx"
```

**Baixar só o áudio de um único vídeo:**
```bash
python baixar_v2.py --url "https://www.youtube.com/watch?v=xxxxxxxxxxx" --mp3
```

**Apontar manualmente para um FFmpeg específico:**
```bash
python baixar_v2.py --mp3 --ffmpeg-location "C:\ffmpeg\bin"
```

---

## 6. Arquivos e pastas gerados

| Caminho          | Conteúdo                                                                 |
|-------------------|---------------------------------------------------------------------------|
| `videos/`         | Vídeos MP4 baixados (modo padrão).                                       |
| `audios/`         | Áudios MP3 baixados (modo `--mp3`).                                      |
| `lista.txt`       | Fila de URLs pendentes (criado automaticamente se não existir).          |
| `url_historico.txt` | Histórico de URLs já baixadas com sucesso, em qualquer modo.           |
| `log.txt`         | Log detalhado de cada execução (info, avisos e erros com stack trace).   |

> `lista.txt`/`url_historico.txt`/`log.txt` só são tocados quando a fonte
> das URLs é o arquivo de lista. Quando você usa `--url` ou `--playlist`,
> apenas `url_historico.txt` e `log.txt` são atualizados — nada é
> gravado/removido de `lista.txt`.

---

## 7. Comportamento em caso de falha

- Cada URL tem até **3 tentativas automáticas**, com espera crescente
  entre elas (5s, depois 10s).
- Há uma pausa de **2 segundos** entre uma URL e a próxima, para reduzir
  o risco de bloqueio temporário por excesso de requisições.
- Se uma URL falhar mesmo após as tentativas, ela é registrada em
  `log.txt` com o erro completo. No modo `lista.txt`, ela continua na
  lista para a próxima execução; nos modos `--url`/`--playlist`, ela só
  aparece no resumo final e no log.

---

## Problemas comuns

### "Encoder not found" ao gerar MP3

O FFmpeg encontrado no seu sistema não tem o encoder `libmp3lame`
compilado (comum quando há mais de um FFmpeg instalado, ou quando é uma
build "enxuta" voltada para hardware específico, ex: NVENC/QSV/AMF).

**Solução:** baixe uma build "full" ou "essentials" da
[gyan.dev](https://www.gyan.dev/ffmpeg/builds/) e use
`--ffmpeg-location "C:\caminho\bin"` apontando para ela, ou ajuste o PATH
do Windows para priorizar essa instalação.

### "FFmpeg não foi encontrado"

O FFmpeg não está no PATH do sistema. Instale-o (veja a seção
[Instalação](#23-instalar-o-ffmpeg)) ou informe o caminho manualmente com
`--ffmpeg-location`.

### Download falha com erro de arquivo/caminho no Windows

Improvável nas versões atuais do script — títulos de vídeo com caracteres
inválidos para nome de arquivo (`: ? " < > |`) já são sanitizados
automaticamente antes de salvar.

---

## Aviso de uso

Este script é fornecido para uso pessoal (backup de conteúdo próprio,
material educacional, etc.). Respeite os Termos de Serviço do YouTube e
os direitos autorais do conteúdo baixado — o uso é de responsabilidade
de quem executa o script.
