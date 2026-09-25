from pathlib import Path
import argparse
import logging
import subprocess
import sys
import shutil
import time

from tqdm import tqdm
import yt_dlp


# ============================================================
# CONFIGURAÇÃO
# ============================================================

ARQUIVO_LISTA = Path("lista.txt")
ARQUIVO_HISTORICO = Path("url_historico.txt")
ARQUIVO_LOG = Path("log.txt")
PASTA_SAIDA_VIDEO = Path("videos")
PASTA_SAIDA_AUDIO = Path("audios")

# Tentativas automáticas por URL em caso de falha, com backoff.
TENTATIVAS_MAX = 3
ESPERA_ENTRE_TENTATIVAS = 5  # segundos, multiplicado pelo nº da tentativa

# Pausa entre uma URL e outra, para reduzir risco de rate-limit.
PAUSA_ENTRE_DOWNLOADS = 2  # segundos


# Máximo de 1080p / 1920x1080 para modo vídeo.
FORMATO_VIDEO = (
    "bv*[height<=1080][width<=1920][ext=mp4][vcodec^=avc1]"
    "+ba[ext=m4a]/"
    "bv*[height<=1080][width<=1920]"
    "+ba/"
    "b[height<=1080][width<=1920]"
)

# Melhor áudio disponível para conversão para MP3.
FORMATO_MP3 = "bestaudio/best"


# ============================================================
# LOG
# ============================================================

logging.basicConfig(
    filename=ARQUIVO_LOG,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8"
)


# ============================================================
# ARGUMENTOS
# ============================================================

def argumentos():
    parser = argparse.ArgumentParser(
        description=(
            "Downloader de YouTube. "
            "Por padrão baixa vídeo MP4 até 1080p. "
            "Use --mp3 para extrair áudio em MP3."
        )
    )

    parser.add_argument(
        "--mp3",
        action="store_true",
        help="Baixa o melhor áudio disponível e converte para MP3."
    )

    parser.add_argument(
        "--ffmpeg-location",
        default=None,
        help=(
            "Caminho da pasta 'bin' do FFmpeg a ser usado "
            "(útil quando há mais de um ffmpeg instalado no PATH "
            "e o padrão não possui suporte a MP3)."
        )
    )

    parser.add_argument(
        "--list",
        dest="lista",
        default=None,
        metavar="ARQUIVO",
        help=(
            "Caminho customizado para o arquivo de URLs "
            "(padrão: lista.txt)."
        )
    )

    parser.add_argument(
        "--playlist",
        dest="playlist_url",
        default=None,
        metavar="URL",
        help=(
            "URL de uma playlist do YouTube. Baixa todos os "
            "vídeos dela (ou só o áudio, com --mp3), sem "
            "precisar passar por lista.txt."
        )
    )

    parser.add_argument(
        "--url",
        dest="url_unica",
        default=None,
        metavar="URL",
        help=(
            "URL de um único vídeo do YouTube. Baixa só ele "
            "(ou só o áudio, com --mp3), sem precisar passar "
            "por lista.txt."
        )
    )

    return parser.parse_args()


# ============================================================
# FUNÇÕES DE ARQUIVO
# ============================================================

def carregar_urls():
    """
    Lê lista.txt.

    Ignora:
    - linhas vazias
    - linhas iniciadas com #

    Retorna:
        list[str]
    """

    if not ARQUIVO_LISTA.exists():
        ARQUIVO_LISTA.write_text("", encoding="utf-8")

        print(
            f"[INFO] {ARQUIVO_LISTA} não existia. "
            "Arquivo criado."
        )

        return []

    urls = []

    with ARQUIVO_LISTA.open("r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()

            if not linha:
                continue

            if linha.startswith("#"):
                continue

            if not linha.startswith(("http://", "https://")):
                print(
                    f"[AVISO] Linha ignorada "
                    f"(não parece uma URL): {linha}"
                )

                logging.warning(
                    "Linha ignorada em %s (não é URL): %s",
                    ARQUIVO_LISTA,
                    linha
                )

                continue

            urls.append(linha)

    return urls


def salvar_lista(urls):
    """
    Reescreve lista.txt somente com as URLs
    que ainda precisam ser processadas.
    """

    with ARQUIVO_LISTA.open("w", encoding="utf-8") as arquivo:
        for url in urls:
            arquivo.write(url + "\n")


def adicionar_historico(url):
    """
    Adiciona uma URL concluída ao histórico.
    """

    with ARQUIVO_HISTORICO.open("a", encoding="utf-8") as arquivo:
        arquivo.write(url + "\n")


def obter_urls_playlist(url_playlist):
    """
    Expande uma URL de playlist do YouTube em uma lista de
    URLs individuais de vídeo (sem baixar nada ainda).
    """

    opcoes = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            info = ydl.extract_info(
                url_playlist,
                download=False
            )

    except Exception as erro:

        print(
            "[ERRO] Não foi possível ler a playlist:"
        )
        print(str(erro))

        logging.error(
            "Falha ao expandir playlist %s: %s",
            url_playlist,
            erro,
            exc_info=True
        )

        return []

    entradas = info.get("entries") or []

    urls = []

    for entrada in entradas:

        if not entrada:
            continue

        video_id = entrada.get("id")

        if video_id:
            urls.append(
                f"https://www.youtube.com/watch?v={video_id}"
            )
        elif entrada.get("url"):
            urls.append(entrada["url"])

    return urls


def localizar_ffmpeg(caminho_manual):
    """
    Resolve qual ffmpeg será usado (manual, se informado,
    ou o primeiro encontrado no PATH).
    """

    if caminho_manual:
        exe = Path(caminho_manual) / "ffmpeg.exe"
        if not exe.exists():
            exe = Path(caminho_manual) / "ffmpeg"
        return str(exe) if exe.exists() else None

    return shutil.which("ffmpeg")


def ffmpeg_suporta_mp3(caminho_ffmpeg):
    """
    Confirma que o binário do ffmpeg encontrado realmente
    possui o encoder libmp3lame. Sem isso, a conversão
    para MP3 falha com "Encoder not found", mesmo que o
    ffmpeg exista no PATH (ex: quando há mais de uma
    instalação e a "errada" é encontrada primeiro).
    """

    try:
        resultado = subprocess.run(
            [caminho_ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return "libmp3lame" in resultado.stdout

    except Exception:
        return False


# ============================================================
# BARRA DE PROGRESSO
# ============================================================

class ProgressBar:

    def __init__(self):
        self.progress = None

    def hook(self, data):

        status = data.get("status")

        if status == "downloading":

            total = data.get("total_bytes")
            downloaded = data.get("downloaded_bytes", 0)

            if not total:
                total = data.get("total_bytes_estimate")

            if self.progress is None:

                self.progress = tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc="Download",
                    leave=True
                )

            if total and self.progress.total != total:
                self.progress.total = total

            delta = downloaded - self.progress.n

            if delta > 0:
                self.progress.update(delta)

        elif status == "finished":

            if self.progress:
                self.progress.close()

            self.progress = None

            print(
                "\n[INFO] Download concluído. "
                "Iniciando processamento..."
            )

    def fechar(self):

        if self.progress:
            self.progress.close()
            self.progress = None

    def hook_pos_processamento(self, data):
        """
        Dá feedback durante a etapa de FFmpeg (remux/conversão),
        que pode demorar em arquivos grandes e ficava muda antes.
        """

        status = data.get("status")
        nome = data.get("postprocessor", "FFmpeg")

        if status == "started":
            print(f"[INFO] Processando com {nome}...")

        elif status == "finished":
            print(f"[INFO] {nome} concluído.")


# ============================================================
# DOWNLOAD
# ============================================================

def baixar_video(url, ffmpeg_location=None):

    progress = ProgressBar()

    PASTA_SAIDA_VIDEO.mkdir(
        parents=True,
        exist_ok=True
    )

    opcoes = {

        # ----------------------------------------------------
        # Formato
        # ----------------------------------------------------

        "format": FORMATO_VIDEO,

        # ----------------------------------------------------
        # Saída
        # ----------------------------------------------------

        "outtmpl": str(
            PASTA_SAIDA_VIDEO / "%(title)s.%(ext)s"
        ),

        # ----------------------------------------------------
        # MP4
        # ----------------------------------------------------

        "merge_output_format": "mp4",

        # ----------------------------------------------------
        # Barra de progresso
        # ----------------------------------------------------

        "progress_hooks": [
            progress.hook
        ],

        "postprocessor_hooks": [
            progress.hook_pos_processamento
        ],

        # ----------------------------------------------------
        # Continua downloads interrompidos
        # ----------------------------------------------------

        "continuedl": True,

        # ----------------------------------------------------
        # Não sobrescreve arquivo já existente
        # ----------------------------------------------------

        "overwrites": False,

        # ----------------------------------------------------
        # Sanitiza nomes de arquivo para o Windows
        # (evita falhas com títulos que têm : ? " < > | etc.)
        # ----------------------------------------------------

        "windowsfilenames": True,

        # ----------------------------------------------------
        # Saída
        # ----------------------------------------------------

        "quiet": True,
        "no_warnings": False,

        # ----------------------------------------------------
        # Compatibilidade
        # ----------------------------------------------------

        "noplaylist": True,

        # ----------------------------------------------------
        # Timeout
        # ----------------------------------------------------

        "socket_timeout": 30,

        # ----------------------------------------------------
        # Tentativas automáticas
        # ----------------------------------------------------

        "retries": 5,
        "fragment_retries": 5,

        # ----------------------------------------------------
        # FFmpeg
        # ----------------------------------------------------

        "postprocessors": [
            {
                "key": "FFmpegVideoRemuxer",
                "preferedformat": "mp4"
            },
            {
                "key": "FFmpegMetadata"
            }
        ],
    }

    if ffmpeg_location:
        opcoes["ffmpeg_location"] = ffmpeg_location

    try:

        print()
        print("-" * 70)
        print("URL:")
        print(url)
        print("-" * 70)

        logging.info("Iniciando download de vídeo: %s", url)

        with yt_dlp.YoutubeDL(opcoes) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            titulo = info.get(
                "title",
                "Título desconhecido"
            )

            print()
            print(f"[OK] Vídeo concluído: {titulo}")

            logging.info(
                "Vídeo concluído: %s | %s",
                url,
                titulo
            )

        progress.fechar()

        return True

    except Exception as erro:

        progress.fechar()

        mensagem = str(erro)

        print()
        print("[ERRO] Falha ao baixar vídeo:")
        print(mensagem)

        logging.error(
            "Falha no vídeo: %s | %s",
            url,
            mensagem,
            exc_info=True
        )

        return False


# ============================================================
# DOWNLOAD / CONVERSÃO MP3
# ============================================================

def baixar_mp3(url, ffmpeg_location=None):

    progress = ProgressBar()

    PASTA_SAIDA_AUDIO.mkdir(
        parents=True,
        exist_ok=True
    )

    opcoes = {

        # ----------------------------------------------------
        # Melhor áudio disponível
        # ----------------------------------------------------

        "format": FORMATO_MP3,

        # ----------------------------------------------------
        # Saída
        # O yt-dlp usará o nome original e o postprocessor
        # converterá a extensão final para .mp3.
        # ----------------------------------------------------

        "outtmpl": str(
            PASTA_SAIDA_AUDIO / "%(title)s.%(ext)s"
        ),

        # ----------------------------------------------------
        # Barra de progresso
        # ----------------------------------------------------

        "progress_hooks": [
            progress.hook
        ],

        "postprocessor_hooks": [
            progress.hook_pos_processamento
        ],

        # ----------------------------------------------------
        # Continua downloads interrompidos
        # ----------------------------------------------------

        "continuedl": True,

        # ----------------------------------------------------
        # Não sobrescreve arquivo já existente
        # ----------------------------------------------------

        "overwrites": False,

        # ----------------------------------------------------
        # Sanitiza nomes de arquivo para o Windows
        # (evita falhas com títulos que têm : ? " < > | etc.)
        # ----------------------------------------------------

        "windowsfilenames": True,

        # ----------------------------------------------------
        # Saída
        # ----------------------------------------------------

        "quiet": True,
        "no_warnings": False,

        # ----------------------------------------------------
        # Compatibilidade
        # ----------------------------------------------------

        "noplaylist": True,

        # ----------------------------------------------------
        # Timeout
        # ----------------------------------------------------

        "socket_timeout": 30,

        # ----------------------------------------------------
        # Tentativas automáticas
        # ----------------------------------------------------

        "retries": 5,
        "fragment_retries": 5,

        # ----------------------------------------------------
        # FFmpeg -> MP3
        # ----------------------------------------------------

        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            },
            {
                "key": "FFmpegMetadata"
            }
        ],

        # Mantém o .webm/.m4a original caso a conversão falhe,
        # em vez de apagar a fonte e deixar nada na pasta.
        "keepvideo": True,
    }

    if ffmpeg_location:
        opcoes["ffmpeg_location"] = ffmpeg_location

    try:

        print()
        print("-" * 70)
        print("URL:")
        print(url)
        print("-" * 70)

        logging.info("Iniciando download MP3: %s", url)

        with yt_dlp.YoutubeDL(opcoes) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            titulo = info.get(
                "title",
                "Título desconhecido"
            )

            print()
            print(f"[OK] MP3 concluído: {titulo}")

            logging.info(
                "MP3 concluído: %s | %s",
                url,
                titulo
            )

        progress.fechar()

        return True

    except Exception as erro:

        progress.fechar()

        mensagem = str(erro)

        print()
        print("[ERRO] Falha ao baixar/converter MP3:")
        print(mensagem)

        logging.error(
            "Falha no MP3: %s | %s",
            url,
            mensagem,
            exc_info=True
        )

        return False


# ============================================================
# RETRY
# ============================================================

def baixar_com_retry(funcao_download, url, ffmpeg_location):
    """
    Chama funcao_download (baixar_video ou baixar_mp3) até
    TENTATIVAS_MAX vezes, com espera crescente entre tentativas,
    antes de considerar a URL como falha definitiva.
    """

    for tentativa in range(1, TENTATIVAS_MAX + 1):

        if funcao_download(url, ffmpeg_location):
            return True

        if tentativa < TENTATIVAS_MAX:

            espera = ESPERA_ENTRE_TENTATIVAS * tentativa

            print(
                f"[AVISO] Tentativa {tentativa}/{TENTATIVAS_MAX} "
                f"falhou. Tentando novamente em {espera}s..."
            )

            logging.warning(
                "Tentativa %d/%d falhou para %s. Aguardando %ds.",
                tentativa,
                TENTATIVAS_MAX,
                url,
                espera
            )

            time.sleep(espera)

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    global ARQUIVO_LISTA

    args = argumentos()

    if args.lista:
        ARQUIVO_LISTA = Path(args.lista)

    modo = "MP3" if args.mp3 else "VÍDEO MP4"

    print("=" * 70)
    print("YouTube Downloader")
    print(f"Windows | Modo: {modo}")
    print("=" * 70)
    print()

    # --------------------------------------------------------
    # Verificação do FFmpeg
    # --------------------------------------------------------

    caminho_ffmpeg = localizar_ffmpeg(args.ffmpeg_location)

    if caminho_ffmpeg is None:

        print(
            "[ERRO] FFmpeg não foi encontrado."
        )

        print()
        print(
            "Verifique a configuração do FFmpeg "
            "nas variáveis de ambiente do Windows, "
            "ou informe --ffmpeg-location \"C:\\caminho\\bin\"."
        )

        logging.error(
            "FFmpeg não encontrado."
        )

        sys.exit(1)

    print(f"[INFO] FFmpeg em uso: {caminho_ffmpeg}")

    if args.mp3 and not ffmpeg_suporta_mp3(caminho_ffmpeg):

        print(
            "[ERRO] Este FFmpeg não possui o encoder "
            "'libmp3lame' (necessário para gerar MP3)."
        )

        print()
        print(
            "Isso costuma acontecer quando há mais de um "
            "ffmpeg instalado (ex: trazido por outro programa "
            "ou biblioteca Python) e o PATH está apontando "
            "para uma versão sem suporte a MP3."
        )

        print()
        print(
            "Baixe um build 'full' ou 'essentials' em "
            "https://www.gyan.dev/ffmpeg/builds/ e informe "
            "a pasta com --ffmpeg-location, ou ajuste o PATH "
            "para priorizar essa versão."
        )

        logging.error(
            "FFmpeg sem suporte a libmp3lame: %s",
            caminho_ffmpeg
        )

        sys.exit(1)

    ffmpeg_location = str(Path(caminho_ffmpeg).parent)

    # --------------------------------------------------------
    # Carrega URLs
    # Prioridade: --url > --playlist > lista.txt (ou --list)
    # --------------------------------------------------------

    usando_arquivo_lista = not (args.url_unica or args.playlist_url)

    outras_fontes_ignoradas = [
        nome
        for nome, valor in (
            ("--playlist", args.playlist_url),
            ("--list", args.lista),
        )
        if valor
    ]

    if args.url_unica:

        if outras_fontes_ignoradas:
            print(
                f"[AVISO] --url foi informado junto com "
                f"{' e '.join(outras_fontes_ignoradas)}; "
                "usando apenas a URL única."
            )

        urls = [args.url_unica]

    elif args.playlist_url:

        if args.lista:
            print(
                "[AVISO] --playlist e --list foram informados juntos; "
                "usando a playlist e ignorando o arquivo."
            )

        print(
            f"[INFO] Lendo playlist: {args.playlist_url}"
        )

        urls = obter_urls_playlist(args.playlist_url)

        if not urls:

            print(
                "[INFO] Nenhum vídeo encontrado na playlist "
                "(ou ela é privada/indisponível)."
            )

            return

        print(
            f"[INFO] Vídeos encontrados na playlist: {len(urls)}"
        )

    else:

        urls = carregar_urls()

        if not urls:

            print(
                "[INFO] Nenhuma URL encontrada em lista.txt."
            )

            return

    pasta_saida = PASTA_SAIDA_AUDIO if args.mp3 else PASTA_SAIDA_VIDEO

    print(
        f"[INFO] URLs pendentes: {len(urls)}"
    )

    print(
        f"[INFO] Pasta de saída: "
        f"{pasta_saida.resolve()}"
    )

    print()

    sucessos = 0
    erros = 0

    # Trabalhamos sobre uma cópia para poder modificar
    # a lista original durante o processamento.

    pendentes = urls.copy()

    for numero, url in enumerate(
        urls,
        start=1
    ):

        print()
        print(
            f"[{numero}/{len(urls)}] "
            f"Processando..."
        )

        if args.mp3:
            funcao_download = baixar_mp3
        else:
            funcao_download = baixar_video

        sucesso = baixar_com_retry(
            funcao_download,
            url,
            ffmpeg_location
        )

        if sucesso:

            sucessos += 1

            # ------------------------------------------------
            # Adiciona ao histórico
            # ------------------------------------------------

            adicionar_historico(url)

            # ------------------------------------------------
            # Remove da lista de pendentes
            # ------------------------------------------------

            if url in pendentes:
                pendentes.remove(url)

            print(
                "[OK] URL adicionada a "
                "url_historico.txt"
            )

            if usando_arquivo_lista:

                # --------------------------------------------
                # Atualiza lista.txt imediatamente
                # --------------------------------------------

                salvar_lista(pendentes)

                print(
                    "[OK] URL removida de lista.txt"
                )

        else:

            erros += 1

            if usando_arquivo_lista:

                # A URL permanece em pendentes/lista.txt.

                print(
                    "[ERRO] URL mantida em lista.txt"
                )

                salvar_lista(pendentes)

            else:

                print(
                    "[ERRO] Falha nesta URL "
                    "(veja log.txt para detalhes)."
                )

        if numero < len(urls):
            time.sleep(PAUSA_ENTRE_DOWNLOADS)

    # ========================================================
    # RESUMO
    # ========================================================

    print()
    print("=" * 70)
    print("PROCESSAMENTO FINALIZADO")
    print("=" * 70)

    print(
        f"Modo        : {modo}"
    )

    print(
        f"Processadas : {len(urls)}"
    )

    print(
        f"Sucesso     : {sucessos}"
    )

    print(
        f"Erro        : {erros}"
    )

    print(
        f"Pendentes   : {len(pendentes)}"
    )

    print()

    if usando_arquivo_lista:
        print(
            f"Lista atual : {ARQUIVO_LISTA.resolve()}"
        )
    elif args.url_unica:
        print(
            f"Origem      : URL única ({args.url_unica})"
        )
    else:
        print(
            f"Origem      : playlist ({args.playlist_url})"
        )

    print(
        f"Histórico   : {ARQUIVO_HISTORICO.resolve()}"
    )

    print(
        f"Log         : {ARQUIVO_LOG.resolve()}"
    )

    print(
        f"Saída       : {pasta_saida.resolve()}"
    )

    print("=" * 70)

    logging.info(
        "Processamento finalizado | "
        "Modo=%s | Total=%d | Sucesso=%d | "
        "Erros=%d | Pendentes=%d",
        modo,
        len(urls),
        sucessos,
        erros,
        len(pendentes)
    )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()
