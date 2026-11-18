# Trabalho Final de Sistemas Operacionais
# Simulador de escalonamento Round Robin com Feedback
#
# Como rodar:
#   python src/escalonador.py
#   python src/escalonador.py --seed 7 --processos 8 --quantum 4
#   python src/escalonador.py --entrada input/exemplo.txt
#   python src/escalonador.py --saida output/resultado.txt
#   python src/escalonador.py --sem-filas

import random
import sys

# ---------- Premissas ----------
QUANTUM = 3          # quantum padrao (unidades de tempo)
NUM_PROCESSOS = 6    # quantidade padrao de processos aleatorios
MAX_PROCESSOS = 20
SEED = 42            # semente padrao
CPU_MIN = 4          # tempo de CPU de cada processo: de 4 a 12
CPU_MAX = 12
CHEGADA_MAX = 10     # processos chegam entre t=0 e t=10
MAX_IO = 2           # cada processo faz de 0 a 2 I/Os

DISPOSITIVOS = ["DISCO", "FITA", "IMPRESSORA"]
DURACAO_IO = {"DISCO": 3, "FITA": 5, "IMPRESSORA": 8}
VOLTA_PARA = {"DISCO": "BAIXA", "FITA": "ALTA", "IMPRESSORA": "ALTA"}
ARTIGO = {"DISCO": "do", "FITA": "da", "IMPRESSORA": "da"}  # so para as mensagens

AJUDA = """Uso: python src/escalonador.py [opcoes]

Opções:
  --quantum N      fatia de tempo (padrão: 3)
  --processos N    quantidade de processos aleatórios (padrão: 6, máx: 20)
  --seed N         semente aleatória (padrão: 42)
  --entrada ARQ    lê os processos de um arquivo (ex.: input/exemplo.txt)
  --saida ARQ      salva a saída também em arquivo (ex.: output/resultado.txt)
  --sem-filas      não imprime o estado das filas a cada evento
  --help           mostra esta ajuda"""

# tudo que e impresso fica guardado aqui, para salvar com --saida
linhas_saida = []


def escrever(texto=""):
    print(texto)
    linhas_saida.append(texto)


def log(t, texto):
    escrever(f"[t={t:03d}] {texto}")


def erro(mensagem):
    print("Erro:", mensagem)
    sys.exit(1)


# ---------- PCB ----------

def criar_processo(pid, ppid, chegada, tempo_cpu, ios):
    # ios e uma lista de (instante, dispositivo).
    # instante = quanto de CPU o processo ja usou quando pede o I/O.
    # Ex: (2, "DISCO") -> depois de usar 2 u.t. de CPU ele pede o disco.
    return {
        "pid": pid,
        "ppid": ppid,
        "status": "NOVO",
        "prioridade": "ALTA",
        "chegada": chegada,
        "tempo_cpu": tempo_cpu,
        "restante": tempo_cpu,   # quanto falta de CPU
        "executado": 0,          # quanto ja usou de CPU
        "ios": sorted(ios),
        "prox_io": 0,            # posicao do proximo I/O na lista
        "inicio": None,          # primeira vez que pegou a CPU
        "fim": None,
        "espera": 0,             # tempo parado nas filas ALTA/BAIXA
        "preempcoes": 0,
    }


def proximo_io(p):
    # devolve (instante, dispositivo) do proximo I/O, ou None se nao tem mais
    if p["prox_io"] < len(p["ios"]):
        return p["ios"][p["prox_io"]]
    return None


def colocar_na_fila(p, prioridade, alta, baixa):
    # o processo fica PRONTO e entra no fim da fila ALTA ou BAIXA
    p["status"] = "PRONTO"
    p["prioridade"] = prioridade
    if prioridade == "ALTA":
        alta.append(p)
    else:
        baixa.append(p)


def texto_ios(p):
    if len(p["ios"]) == 0:
        return "nenhum"
    partes = []
    for instante, disp in p["ios"]:
        partes.append(f"{disp}@{instante}")
    return ", ".join(partes)


# ---------- Criacao dos processos ----------

def gerar_processos(n):
    chegadas = []
    for i in range(n):
        chegadas.append(random.randint(0, CHEGADA_MAX))
    chegadas.sort()
    chegadas[0] = 0  # sempre tem um processo em t=0

    processos = []
    for i in range(n):
        pid = i + 1
        # o P1 e filho do sistema (0); os outros podem ser filhos do sistema
        # ou de algum processo criado antes
        if pid == 1 or random.random() < 0.4:
            ppid = 0
        else:
            ppid = random.randint(1, pid - 1)

        tempo_cpu = random.randint(CPU_MIN, CPU_MAX)
        qtd_io = random.randint(0, MAX_IO)
        instantes = random.sample(range(1, tempo_cpu), qtd_io)
        instantes.sort()
        ios = []
        for instante in instantes:
            ios.append((instante, random.choice(DISPOSITIVOS)))

        processos.append(criar_processo(pid, ppid, chegadas[i], tempo_cpu, ios))
    return processos


def ler_arquivo(caminho):
    # formato de cada linha: PID PPID CHEGADA TEMPO_CPU [instante:DISPOSITIVO ...]
    # o que vem depois de # e comentario
    try:
        arquivo = open(caminho, encoding="utf-8")
        linhas = arquivo.readlines()
        arquivo.close()
    except OSError:
        erro(f"não foi possível abrir o arquivo '{caminho}'")

    processos = []
    pids = []
    num = 0
    for linha in linhas:
        num += 1
        linha = linha.split("#")[0].strip()
        if linha == "":
            continue

        partes = linha.split()
        if len(partes) < 4:
            erro(f"linha {num}: esperado PID PPID CHEGADA TEMPO_CPU")
        try:
            pid = int(partes[0])
            ppid = int(partes[1])
            chegada = int(partes[2])
            tempo_cpu = int(partes[3])
        except ValueError:
            erro(f"linha {num}: PID, PPID, CHEGADA e TEMPO_CPU devem ser números inteiros")

        if pid in pids:
            erro(f"linha {num}: PID {pid} repetido")
        if tempo_cpu <= 0 or chegada < 0:
            erro(f"linha {num}: tempos devem ser positivos")

        ios = []
        instantes_usados = []
        for item in partes[4:]:
            if ":" not in item:
                erro(f"linha {num}: I/O deve estar no formato instante:DISPOSITIVO")
            instante, disp = item.split(":", 1)
            disp = disp.upper()
            try:
                instante = int(instante)
            except ValueError:
                erro(f"linha {num}: instante de I/O inválido '{item}'")
            if disp not in DISPOSITIVOS:
                erro(f"linha {num}: dispositivo inválido '{disp}'")
            if instante < 1 or instante >= tempo_cpu:
                erro(f"linha {num}: instante de I/O deve estar entre 1 e {tempo_cpu - 1}")
            if instante in instantes_usados:
                erro(f"linha {num}: dois I/Os no mesmo instante {instante}")
            instantes_usados.append(instante)
            ios.append((instante, disp))

        pids.append(pid)
        processos.append(criar_processo(pid, ppid, chegada, tempo_cpu, ios))

    if len(processos) == 0:
        erro("o arquivo não tem nenhum processo")
    if len(processos) > MAX_PROCESSOS:
        erro(f"máximo de {MAX_PROCESSOS} processos")
    return processos


# ---------- Impressao ----------

def imprimir_tabela_inicial(processos):
    escrever("Processos (PCB inicial):")
    escrever(f"  {'PID':>3} {'PPID':>4} {'CHEGADA':>7} {'CPU':>4}  {'STATUS':<6} {'PRIOR.':<6} I/O (dispositivo@instante de CPU)")
    for p in processos:
        escrever(f"  {p['pid']:>3} {p['ppid']:>4} {p['chegada']:>7} {p['tempo_cpu']:>4}  "
                 f"{p['status']:<6} {p['prioridade']:<6} {texto_ios(p)}")
    escrever()


def nomes(lista):
    # [P1, P2] -> "P1,P2"
    texto = ""
    for p in lista:
        if texto != "":
            texto += ","
        texto += "P" + str(p["pid"])
    return texto


def estado_filas(alta, baixa, fila_io, atendendo, executando):
    if executando is None:
        cpu = "ociosa"
    else:
        cpu = "P" + str(executando["pid"])
    texto = f"CPU={cpu}  ALTA=[{nomes(alta)}]  BAIXA=[{nomes(baixa)}]"

    for d in DISPOSITIVOS:
        # o * marca quem esta sendo atendido pelo dispositivo
        conteudo = nomes(fila_io[d])
        if atendendo[d] is not None:
            atual = "P" + str(atendendo[d]["pid"]) + "*"
            if conteudo == "":
                conteudo = atual
            else:
                conteudo = atual + "," + conteudo
        texto += f"  {d}=[{conteudo}]"
    return texto


def imprimir_gantt(linha_tempo):
    # junta as unidades seguidas do mesmo processo em intervalos, ex: "0-2 P1"
    intervalos = []
    inicio = 0
    for t in range(1, len(linha_tempo) + 1):
        if t == len(linha_tempo) or linha_tempo[t] != linha_tempo[inicio]:
            if linha_tempo[inicio] is None:
                nome = "--"
            else:
                nome = "P" + str(linha_tempo[inicio])
            intervalos.append(f"{inicio}-{t} {nome}")
            inicio = t

    escrever("Linha do tempo da CPU (Gantt)  -- = CPU ociosa")
    # 7 intervalos por linha para nao ficar muito comprido
    for i in range(0, len(intervalos), 7):
        escrever("  " + " | ".join(intervalos[i:i + 7]))
    escrever()


# ---------- Simulacao ----------

def simular(processos, quantum, mostrar_filas):
    alta = []
    baixa = []
    # cada dispositivo tem sua fila e atende um processo por vez
    fila_io = {"DISCO": [], "FITA": [], "IMPRESSORA": []}
    atendendo = {"DISCO": None, "FITA": None, "IMPRESSORA": None}
    tempo_io = {"DISCO": 0, "FITA": 0, "IMPRESSORA": 0}  # quanto falta para terminar

    # processos que ainda nao chegaram, em ordem de chegada
    novos = sorted(processos, key=lambda p: (p["chegada"], p["pid"]))

    executando = None
    quantum_usado = 0
    finalizados = 0
    t = 0

    linha_tempo = []   # quem usou a CPU em cada instante (None = ociosa)
    cpu_ociosa = 0
    trocas = 0
    preempcoes = 0
    eventos_io = {"DISCO": 0, "FITA": 0, "IMPRESSORA": 0}

    while True:
        teve_evento = False

        # 1) processos que chegam agora vao para a fila ALTA
        while len(novos) > 0 and novos[0]["chegada"] <= t:
            p = novos.pop(0)
            colocar_na_fila(p, "ALTA", alta, baixa)
            log(t, f"P{p['pid']} criado (PPID={p['ppid']}, CPU={p['tempo_cpu']}, "
                   f"I/O: {texto_ios(p)}) -> fila ALTA")
            teve_evento = True

        # 2) quem terminou o I/O volta para a fila do dispositivo
        for d in DISPOSITIVOS:
            p = atendendo[d]
            if p is not None and tempo_io[d] == 0:
                atendendo[d] = None
                destino = VOLTA_PARA[d]
                colocar_na_fila(p, destino, alta, baixa)
                log(t, f"P{p['pid']} retornou {ARTIGO[d]} {d} -> fila {destino}")
                teve_evento = True

        # 3) ve o que acontece com o processo que esta na CPU
        if executando is not None:
            p = executando
            io = proximo_io(p)
            if p["restante"] == 0:
                # terminou
                p["status"] = "FINALIZADO"
                p["fim"] = t
                finalizados += 1
                executando = None
                log(t, f"P{p['pid']} FINALIZADO (turnaround = {p['fim'] - p['chegada']} u.t.)")
                teve_evento = True
            elif io is not None and io[0] == p["executado"]:
                # chegou a hora de pedir I/O
                d = io[1]
                p["prox_io"] += 1
                p["status"] = "BLOQUEADO"
                fila_io[d].append(p)
                eventos_io[d] += 1
                executando = None
                log(t, f"P{p['pid']} solicitou I/O {d} por {DURACAO_IO[d]} u.t. -> BLOQUEADO")
                teve_evento = True
            elif quantum_usado == quantum:
                # acabou o quantum: preempcao, vai para a fila BAIXA
                p["preempcoes"] += 1
                preempcoes += 1
                colocar_na_fila(p, "BAIXA", alta, baixa)
                executando = None
                log(t, f"P{p['pid']} sofreu preempção (fim do quantum, faltam {p['restante']}) -> fila BAIXA")
                teve_evento = True

        if finalizados == len(processos):
            if mostrar_filas and teve_evento:
                escrever("         " + estado_filas(alta, baixa, fila_io, atendendo, executando))
            break

        # 4) dispositivo livre comeca a atender o proximo da fila dele
        for d in DISPOSITIVOS:
            if atendendo[d] is None and len(fila_io[d]) > 0:
                p = fila_io[d].pop(0)
                atendendo[d] = p
                tempo_io[d] = DURACAO_IO[d]
                log(t, f"{d} inicia atendimento de P{p['pid']} (termina em t={t + DURACAO_IO[d]})")
                teve_evento = True

        # 5) se a CPU esta livre, escolhe o proximo: primeiro ALTA, depois BAIXA
        if executando is None:
            if len(alta) > 0:
                executando = alta.pop(0)
                origem = "ALTA"
            elif len(baixa) > 0:
                executando = baixa.pop(0)
                origem = "BAIXA"

            if executando is not None:
                p = executando
                p["status"] = "EXECUTANDO"
                quantum_usado = 0
                trocas += 1
                if p["inicio"] is None:
                    p["inicio"] = t

                # calcula por quanto tempo ele deve rodar (so para mostrar no log)
                fatia = min(quantum, p["restante"])
                if fatia == quantum:
                    motivo = "quantum"
                else:
                    motivo = "fim do processo"
                io = proximo_io(p)
                if io is not None and io[0] - p["executado"] <= fatia:
                    fatia = io[0] - p["executado"]
                    motivo = f"pedido de I/O {io[1]}"

                log(t, f"CPU executa P{p['pid']} (veio da fila {origem}, restante={p['restante']}) "
                       f"por até {fatia} u.t. [{motivo}]")
                teve_evento = True
            elif len(linha_tempo) == 0 or linha_tempo[-1] is not None:
                # so avisa no comeco do periodo ocioso
                log(t, "CPU ociosa (nenhum processo pronto)")
                teve_evento = True

        if mostrar_filas and teve_evento:
            escrever("         " + estado_filas(alta, baixa, fila_io, atendendo, executando))

        # 6) passa uma unidade de tempo
        if executando is not None:
            executando["restante"] -= 1
            executando["executado"] += 1
            quantum_usado += 1
            linha_tempo.append(executando["pid"])
        else:
            linha_tempo.append(None)
            cpu_ociosa += 1
        for p in alta + baixa:
            p["espera"] += 1
        for d in DISPOSITIVOS:
            if atendendo[d] is not None:
                tempo_io[d] -= 1
        t += 1

    return {
        "tempo_total": t,
        "linha_tempo": linha_tempo,
        "cpu_ociosa": cpu_ociosa,
        "trocas": trocas,
        "preempcoes": preempcoes,
        "eventos_io": eventos_io,
    }


def imprimir_resumo(processos, quantum, r):
    n = len(processos)
    escrever()
    escrever("=" * 78)
    escrever("RESUMO FINAL")
    escrever("=" * 78)
    imprimir_gantt(r["linha_tempo"])

    escrever("Estatísticas por processo:")
    escrever(f"  {'PID':>3} {'PPID':>4} {'CHEG.':>5} {'CPU':>4} {'I/Os':>4} {'INÍCIO':>6} "
             f"{'FIM':>4} {'TURNAROUND':>10} {'ESPERA':>6} {'RESPOSTA':>8} {'PREEMP.':>7}  STATUS")

    soma_turnaround = 0
    soma_espera = 0
    soma_resposta = 0
    qtd_finalizados = 0
    for p in sorted(processos, key=lambda p: p["pid"]):
        turnaround = p["fim"] - p["chegada"]
        resposta = p["inicio"] - p["chegada"]
        soma_turnaround += turnaround
        soma_espera += p["espera"]
        soma_resposta += resposta
        if p["status"] == "FINALIZADO":
            qtd_finalizados += 1
        escrever(f"  {p['pid']:>3} {p['ppid']:>4} {p['chegada']:>5} {p['tempo_cpu']:>4} "
                 f"{len(p['ios']):>4} {p['inicio']:>6} {p['fim']:>4} {turnaround:>10} "
                 f"{p['espera']:>6} {resposta:>8} {p['preempcoes']:>7}  {p['status']}")
    escrever()

    total = r["tempo_total"]
    io = r["eventos_io"]
    total_io = io["DISCO"] + io["FITA"] + io["IMPRESSORA"]
    ociosa_pct = 100 * r["cpu_ociosa"] / total

    escrever("Métricas gerais:")
    escrever(f"  Processos finalizados ........ {qtd_finalizados}/{n}")
    escrever(f"  Tempo total da simulação ..... {total} u.t.")
    escrever(f"  Quantum ...................... {quantum} u.t.")
    escrever(f"  Trocas de contexto ........... {r['trocas']}")
    escrever(f"  Preempções (fim de quantum) .. {r['preempcoes']}")
    escrever(f"  Eventos de I/O ............... DISCO={io['DISCO']}  FITA={io['FITA']}  "
             f"IMPRESSORA={io['IMPRESSORA']}  (total={total_io})")
    escrever(f"  Tempo médio de espera ........ {soma_espera / n:.2f} u.t.")
    escrever(f"  Tempo médio de turnaround .... {soma_turnaround / n:.2f} u.t.")
    escrever(f"  Tempo médio de resposta ...... {soma_resposta / n:.2f} u.t.")
    escrever(f"  CPU ociosa ................... {r['cpu_ociosa']} u.t. ({ociosa_pct:.1f}%)")
    escrever()
    escrever(f"[fim] Processos finalizados: {qtd_finalizados}/{n} | tempo total: {total}")


# ---------- Programa principal ----------

def ler_argumentos():
    opcoes = {
        "quantum": QUANTUM,
        "processos": NUM_PROCESSOS,
        "seed": SEED,
        "entrada": None,
        "saida": None,
        "sem_filas": False,
    }
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--help" or arg == "-h":
            print(AJUDA)
            sys.exit(0)
        elif arg == "--sem-filas":
            opcoes["sem_filas"] = True
            i += 1
        elif arg in ["--quantum", "--processos", "--seed", "--entrada", "--saida"]:
            if i + 1 >= len(args):
                erro(f"faltou o valor de {arg}")
            nome = arg[2:]   # tira o "--"
            valor = args[i + 1]
            if nome in ["quantum", "processos", "seed"]:
                try:
                    valor = int(valor)
                except ValueError:
                    erro(f"{arg} precisa ser um número inteiro")
            opcoes[nome] = valor
            i += 2
        else:
            erro(f"opção desconhecida: {arg} (use --help)")

    if opcoes["quantum"] < 1:
        erro("o quantum deve ser >= 1")
    if opcoes["processos"] < 1 or opcoes["processos"] > MAX_PROCESSOS:
        erro(f"a quantidade de processos deve estar entre 1 e {MAX_PROCESSOS}")
    return opcoes


def main():
    # para os acentos aparecerem certo no terminal
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    opcoes = ler_argumentos()

    if opcoes["entrada"] is not None:
        processos = ler_arquivo(opcoes["entrada"])
        origem = f"arquivo {opcoes['entrada']}"
    else:
        random.seed(opcoes["seed"])
        processos = gerar_processos(opcoes["processos"])
        origem = f"aleatório (seed={opcoes['seed']})"

    escrever("=" * 78)
    escrever("SIMULADOR DE ESCALONAMENTO - ROUND ROBIN COM FEEDBACK")
    escrever("=" * 78)
    escrever(f"[config] quantum={opcoes['quantum']} | processos={len(processos)} | origem={origem}")
    config_io = []
    for d in DISPOSITIVOS:
        config_io.append(f"{d}={DURACAO_IO[d]} u.t. (volta p/ {VOLTA_PARA[d]})")
    escrever("[config] I/O: " + "  ".join(config_io))
    escrever()
    imprimir_tabela_inicial(processos)
    escrever("Linha do tempo dos eventos:")

    resultado = simular(processos, opcoes["quantum"], not opcoes["sem_filas"])
    imprimir_resumo(processos, opcoes["quantum"], resultado)

    if opcoes["saida"] is not None:
        arquivo = open(opcoes["saida"], "w", encoding="utf-8")
        arquivo.write("\n".join(linhas_saida) + "\n")
        arquivo.close()
        print(f"\nSaída salva em {opcoes['saida']}")


main()
