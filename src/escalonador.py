#!/usr/bin/env python3
"""
Trabalho Final de Sistemas Operacionais
Simulador de Escalonamento Round Robin com Feedback

Estrutura (sem orientacao a objetos):
  - Cada processo (PCB) e um dicionario simples.
  - As filas sao deques (collections.deque), estrutura FIFO.
  - A simulacao avanca em unidades de tempo (t = 0, 1, 2, ...).

Uso:
  python src/escalonador.py                         # 6 processos aleatorios, seed 42
  python src/escalonador.py --seed 7 --processos 8  # outra semente / quantidade
  python src/escalonador.py --entrada input/exemplo.txt
  python src/escalonador.py --quantum 4 --saida output/resultado.txt
"""

import argparse
import random
import sys
from collections import deque

# ---------------------------------------------------------------------------
# PREMISSAS (valores padrao, podem ser alterados por linha de comando)
# ---------------------------------------------------------------------------
QUANTUM_PADRAO = 3          # fatia de tempo, em unidades de tempo (u.t.)
NUM_PROCESSOS_PADRAO = 6    # quantidade de processos gerados aleatoriamente
MAX_PROCESSOS = 20          # limite maximo de processos
SEED_PADRAO = 42            # semente aleatoria padrao (reprodutibilidade)
CPU_MIN, CPU_MAX = 4, 12    # faixa do tempo de servico de CPU
CHEGADA_MAX = 10            # processos chegam entre t=0 e t=CHEGADA_MAX
MAX_IO_POR_PROCESSO = 2     # cada processo faz de 0 a 2 operacoes de I/O
LIMITE_TEMPO = 100000       # protecao contra laco infinito

# Dispositivos de I/O: duracao fixa e fila de retorno
DISPOSITIVOS = ["DISCO", "FITA", "IMPRESSORA"]
DURACAO_IO = {"DISCO": 3, "FITA": 5, "IMPRESSORA": 8}
RETORNO_IO = {"DISCO": "BAIXA", "FITA": "ALTA", "IMPRESSORA": "ALTA"}
ARTIGO = {"DISCO": "do", "FITA": "da", "IMPRESSORA": "da"}  # para as mensagens

# Estados possiveis de um processo
NOVO = "NOVO"
PRONTO = "PRONTO"
EXECUTANDO = "EXECUTANDO"
BLOQUEADO = "BLOQUEADO"
FINALIZADO = "FINALIZADO"

# Saida: tudo que e impresso tambem fica guardado para salvar em arquivo
_linhas_saida = []


def escrever(texto=""):
    print(texto)
    _linhas_saida.append(texto)


def log(t, mensagem):
    escrever(f"[t={t:03d}] {mensagem}")


# ---------------------------------------------------------------------------
# PCB (Process Control Block)
# ---------------------------------------------------------------------------
def criar_pcb(pid, ppid, chegada, tempo_cpu, ios):
    """Cria o PCB de um processo como um dicionario.

    ios: lista de tuplas (instante, dispositivo). 'instante' e a quantidade
    de unidades de CPU ja executadas no momento em que o processo pede o I/O.
    Ex.: (2, "DISCO") = depois de usar 2 u.t. de CPU, o processo pede disco.
    """
    return {
        "pid": pid,
        "ppid": ppid,
        "status": NOVO,
        "prioridade": "ALTA",       # fila em que o processo entra/esta
        "chegada": chegada,
        "tempo_cpu": tempo_cpu,     # tempo total de servico de CPU
        "restante": tempo_cpu,      # quanto ainda falta de CPU
        "executado": 0,             # quanto ja usou de CPU
        "ios": sorted(ios),
        "prox_io": 0,               # indice do proximo I/O na lista 'ios'
        # informacoes de controle / estatisticas
        "inicio": None,             # primeira vez que ganhou a CPU
        "fim": None,
        "espera": 0,                # tempo total em fila de prontos
        "preempcoes": 0,
    }


def proximo_io(p):
    """Retorna (instante, dispositivo) do proximo I/O ou None."""
    if p["prox_io"] < len(p["ios"]):
        return p["ios"][p["prox_io"]]
    return None


def descrever_ios(p):
    if not p["ios"]:
        return "nenhum"
    return ", ".join(f"{d}@{i}" for i, d in p["ios"])


# ---------------------------------------------------------------------------
# CRIACAO DOS PROCESSOS
# ---------------------------------------------------------------------------
def gerar_processos(n, rng):
    """Gera n processos aleatorios (reprodutiveis pela semente)."""
    chegadas = sorted(rng.randint(0, CHEGADA_MAX) for _ in range(n))
    chegadas[0] = 0  # sempre ha um processo no instante 0

    processos = []
    for i in range(n):
        pid = i + 1
        # PPID: o primeiro e filho do "sistema" (0); os demais podem ser
        # filhos de um processo criado antes ou do sistema.
        if pid == 1 or rng.random() < 0.4:
            ppid = 0
        else:
            ppid = rng.randint(1, pid - 1)

        tempo_cpu = rng.randint(CPU_MIN, CPU_MAX)
        qtd_io = rng.randint(0, MAX_IO_POR_PROCESSO)
        instantes = sorted(rng.sample(range(1, tempo_cpu), qtd_io))
        ios = [(inst, rng.choice(DISPOSITIVOS)) for inst in instantes]

        processos.append(criar_pcb(pid, ppid, chegadas[i], tempo_cpu, ios))
    return processos


def ler_processos(caminho):
    """Le processos de um arquivo texto.

    Formato de cada linha (linhas com # sao comentarios):
        PID PPID CHEGADA TEMPO_CPU [instante:DISPOSITIVO ...]
    Exemplo:
        3 1 2 7 3:FITA 5:DISCO
    """
    processos = []
    pids = set()
    with open(caminho, encoding="utf-8") as arq:
        for num_linha, linha in enumerate(arq, start=1):
            linha = linha.split("#", 1)[0].strip()
            if not linha:
                continue
            partes = linha.split()
            if len(partes) < 4:
                raise ValueError(f"linha {num_linha}: esperado PID PPID CHEGADA TEMPO_CPU")
            pid, ppid, chegada, tempo_cpu = (int(x) for x in partes[:4])
            if pid in pids:
                raise ValueError(f"linha {num_linha}: PID {pid} repetido")
            if tempo_cpu <= 0 or chegada < 0:
                raise ValueError(f"linha {num_linha}: tempos devem ser positivos")
            ios = []
            for item in partes[4:]:
                inst_txt, disp = item.split(":")
                inst, disp = int(inst_txt), disp.upper()
                if disp not in DISPOSITIVOS:
                    raise ValueError(f"linha {num_linha}: dispositivo inválido '{disp}'")
                if not 0 < inst < tempo_cpu:
                    raise ValueError(
                        f"linha {num_linha}: instante de I/O deve estar entre 1 e {tempo_cpu - 1}")
                if any(inst == i for i, _ in ios):
                    raise ValueError(f"linha {num_linha}: dois I/Os no mesmo instante {inst}")
                ios.append((inst, disp))
            pids.add(pid)
            processos.append(criar_pcb(pid, ppid, chegada, tempo_cpu, ios))
    if not processos:
        raise ValueError("arquivo sem processos")
    if len(processos) > MAX_PROCESSOS:
        raise ValueError(f"máximo de {MAX_PROCESSOS} processos")
    return processos


# ---------------------------------------------------------------------------
# IMPRESSAO
# ---------------------------------------------------------------------------
def imprimir_tabela_inicial(processos):
    escrever("Processos (PCB inicial):")
    escrever(f"  {'PID':>3} {'PPID':>4} {'CHEGADA':>7} {'CPU':>4}  {'STATUS':<6} {'PRIOR.':<6} I/O (dispositivo@instante de CPU)")
    for p in processos:
        escrever(f"  {p['pid']:>3} {p['ppid']:>4} {p['chegada']:>7} {p['tempo_cpu']:>4}  "
                 f"{p['status']:<6} {p['prioridade']:<6} {descrever_ios(p)}")
    escrever()


def nomes(fila):
    return "[" + ",".join(f"P{p['pid']}" for p in fila) + "]"


def estado_filas(alta, baixa, dispositivos, executando):
    cpu = f"P{executando['pid']}" if executando else "ociosa"
    partes = [f"CPU={cpu}", f"ALTA={nomes(alta)}", f"BAIXA={nomes(baixa)}"]
    for d in DISPOSITIVOS:
        disp = dispositivos[d]
        atual = f"P{disp['atual']['pid']}*" if disp["atual"] else ""
        espera = ",".join(f"P{p['pid']}" for p in disp["fila"])
        conteudo = ",".join(x for x in (atual, espera) if x)
        partes.append(f"{d}=[{conteudo}]")
    return "  ".join(partes)


def imprimir_gantt(linha_tempo):
    """Desenha a linha do tempo da CPU (diagrama de Gantt em texto)."""
    segmentos = []  # (inicio, fim, rotulo)
    for t, pid in enumerate(linha_tempo):
        rotulo = f"P{pid}" if pid is not None else "--"
        if segmentos and segmentos[-1][2] == rotulo:
            segmentos[-1][1] = t + 1
        else:
            segmentos.append([t, t + 1, rotulo])

    escrever("Linha do tempo da CPU (Gantt)  -- = CPU ociosa")
    largura_max = 76
    topo, base = "|", ""
    for inicio, fim, rotulo in segmentos:
        w = max(len(rotulo) + 2, len(str(inicio)) + 1, fim - inicio)
        bloco_topo = rotulo.center(w) + "|"
        bloco_base = str(inicio).ljust(w + 1)
        if len(topo) + len(bloco_topo) > largura_max:
            escrever(topo)
            escrever(base + str(inicio))
            escrever()
            topo, base = "|", ""
        topo += bloco_topo
        base += bloco_base
    escrever(topo)
    escrever(base + str(len(linha_tempo)))
    escrever()


# ---------------------------------------------------------------------------
# SIMULACAO
# ---------------------------------------------------------------------------
def simular(processos, quantum, mostrar_filas=True):
    n = len(processos)
    alta = deque()
    baixa = deque()
    # cada dispositivo atende um processo por vez e tem sua propria fila
    dispositivos = {d: {"fila": deque(), "atual": None, "restante": 0} for d in DISPOSITIVOS}

    novos = deque(sorted(processos, key=lambda p: (p["chegada"], p["pid"])))
    executando = None
    quantum_usado = 0
    finalizados = 0
    t = 0

    linha_tempo = []          # PID que usou a CPU em cada unidade de tempo
    cpu_ociosa = 0
    trocas_contexto = 0
    total_preempcoes = 0
    eventos_io = {d: 0 for d in DISPOSITIVOS}

    while True:
        houve_evento = False

        # 1) Chegada de novos processos -> fila ALTA
        while novos and novos[0]["chegada"] <= t:
            p = novos.popleft()
            p["status"] = PRONTO
            p["prioridade"] = "ALTA"
            alta.append(p)
            log(t, f"P{p['pid']} criado (PPID={p['ppid']}, CPU={p['tempo_cpu']}, "
                   f"I/O: {descrever_ios(p)}) -> fila ALTA")
            houve_evento = True

        # 2) Retorno de I/O concluido -> fila definida pelo dispositivo
        for d in DISPOSITIVOS:
            disp = dispositivos[d]
            if disp["atual"] is not None and disp["restante"] == 0:
                p = disp["atual"]
                disp["atual"] = None
                destino = RETORNO_IO[d]
                p["status"] = PRONTO
                p["prioridade"] = destino
                (alta if destino == "ALTA" else baixa).append(p)
                log(t, f"P{p['pid']} retornou {ARTIGO[d]} {d} -> fila {destino}")
                houve_evento = True

        # 3) Verifica o processo que estava na CPU
        if executando is not None:
            p = executando
            io = proximo_io(p)
            if p["restante"] == 0:
                p["status"] = FINALIZADO
                p["fim"] = t
                finalizados += 1
                executando = None
                log(t, f"P{p['pid']} FINALIZADO (turnaround = {p['fim'] - p['chegada']} u.t.)")
                houve_evento = True
            elif io is not None and io[0] == p["executado"]:
                d = io[1]
                p["prox_io"] += 1
                p["status"] = BLOQUEADO
                dispositivos[d]["fila"].append(p)
                eventos_io[d] += 1
                executando = None
                log(t, f"P{p['pid']} solicitou I/O {d} por {DURACAO_IO[d]} u.t. -> BLOQUEADO")
                houve_evento = True
            elif quantum_usado == quantum:
                p["status"] = PRONTO
                p["prioridade"] = "BAIXA"
                p["preempcoes"] += 1
                total_preempcoes += 1
                baixa.append(p)
                executando = None
                log(t, f"P{p['pid']} sofreu preempção (fim do quantum, faltam {p['restante']}) -> fila BAIXA")
                houve_evento = True

        if finalizados == n:
            if mostrar_filas and houve_evento:
                escrever("         " + estado_filas(alta, baixa, dispositivos, executando))
            break

        # 4) Dispositivos livres comecam a atender o proximo da sua fila
        for d in DISPOSITIVOS:
            disp = dispositivos[d]
            if disp["atual"] is None and disp["fila"]:
                p = disp["fila"].popleft()
                disp["atual"] = p
                disp["restante"] = DURACAO_IO[d]
                log(t, f"{d} inicia atendimento de P{p['pid']} (termina em t={t + DURACAO_IO[d]})")
                houve_evento = True

        # 5) Escalonamento: fila ALTA tem preferencia sobre a BAIXA
        if executando is None:
            origem = None
            if alta:
                executando, origem = alta.popleft(), "ALTA"
            elif baixa:
                executando, origem = baixa.popleft(), "BAIXA"
            if executando is not None:
                p = executando
                p["status"] = EXECUTANDO
                quantum_usado = 0
                trocas_contexto += 1
                if p["inicio"] is None:
                    p["inicio"] = t
                fatia = min(quantum, p["restante"])
                io = proximo_io(p)
                motivo = "quantum" if fatia == quantum else "fim do processo"
                if io is not None and io[0] - p["executado"] < fatia:
                    fatia, motivo = io[0] - p["executado"], f"pedido de I/O {io[1]}"
                elif io is not None and io[0] - p["executado"] == fatia:
                    motivo = f"pedido de I/O {io[1]}"
                log(t, f"CPU executa P{p['pid']} (veio da fila {origem}, restante={p['restante']}) "
                       f"por até {fatia} u.t. [{motivo}]")
                houve_evento = True
            elif not linha_tempo or linha_tempo[-1] is not None:
                log(t, "CPU ociosa (nenhum processo pronto)")
                houve_evento = True

        if mostrar_filas and houve_evento:
            escrever("         " + estado_filas(alta, baixa, dispositivos, executando))

        # 6) Avanca uma unidade de tempo
        if executando is not None:
            executando["restante"] -= 1
            executando["executado"] += 1
            quantum_usado += 1
            linha_tempo.append(executando["pid"])
        else:
            linha_tempo.append(None)
            cpu_ociosa += 1
        for p in alta:
            p["espera"] += 1
        for p in baixa:
            p["espera"] += 1
        for d in DISPOSITIVOS:
            if dispositivos[d]["atual"] is not None:
                dispositivos[d]["restante"] -= 1

        t += 1
        if t > LIMITE_TEMPO:
            raise RuntimeError("limite de tempo excedido - verifique os parametros")

    return {
        "tempo_total": t,
        "linha_tempo": linha_tempo,
        "cpu_ociosa": cpu_ociosa,
        "trocas_contexto": trocas_contexto,
        "preempcoes": total_preempcoes,
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
    for p in sorted(processos, key=lambda x: x["pid"]):
        turnaround = p["fim"] - p["chegada"]
        resposta = p["inicio"] - p["chegada"]
        escrever(f"  {p['pid']:>3} {p['ppid']:>4} {p['chegada']:>5} {p['tempo_cpu']:>4} "
                 f"{len(p['ios']):>4} {p['inicio']:>6} {p['fim']:>4} {turnaround:>10} "
                 f"{p['espera']:>6} {resposta:>8} {p['preempcoes']:>7}  {p['status']}")
    escrever()

    total = r["tempo_total"]
    media_turn = sum(p["fim"] - p["chegada"] for p in processos) / n
    media_espera = sum(p["espera"] for p in processos) / n
    media_resp = sum(p["inicio"] - p["chegada"] for p in processos) / n
    ociosa_pct = 100 * r["cpu_ociosa"] / total if total else 0
    io = r["eventos_io"]

    escrever("Métricas gerais:")
    escrever(f"  Processos finalizados ........ {sum(p['status'] == FINALIZADO for p in processos)}/{n}")
    escrever(f"  Tempo total da simulação ..... {total} u.t.")
    escrever(f"  Quantum ...................... {quantum} u.t.")
    escrever(f"  Trocas de contexto ........... {r['trocas_contexto']}")
    escrever(f"  Preempções (fim de quantum) .. {r['preempcoes']}")
    escrever(f"  Eventos de I/O ............... DISCO={io['DISCO']}  FITA={io['FITA']}  "
             f"IMPRESSORA={io['IMPRESSORA']}  (total={sum(io.values())})")
    escrever(f"  Tempo médio de espera ........ {media_espera:.2f} u.t.")
    escrever(f"  Tempo médio de turnaround .... {media_turn:.2f} u.t.")
    escrever(f"  Tempo médio de resposta ...... {media_resp:.2f} u.t.")
    escrever(f"  CPU ociosa ................... {r['cpu_ociosa']} u.t. ({ociosa_pct:.1f}%)")
    escrever()
    escrever(f"[fim] Processos finalizados: {n}/{n} | tempo total: {total}")


# ---------------------------------------------------------------------------
# PROGRAMA PRINCIPAL
# ---------------------------------------------------------------------------
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        description="Simulador de escalonamento Round Robin com Feedback")
    parser.add_argument("--quantum", type=int, default=QUANTUM_PADRAO,
                        help=f"fatia de tempo (padrão: {QUANTUM_PADRAO})")
    parser.add_argument("--processos", type=int, default=NUM_PROCESSOS_PADRAO,
                        help=f"quantidade de processos aleatórios (padrão: {NUM_PROCESSOS_PADRAO}, "
                             f"máx: {MAX_PROCESSOS})")
    parser.add_argument("--seed", type=int, default=SEED_PADRAO,
                        help=f"semente aleatória (padrão: {SEED_PADRAO})")
    parser.add_argument("--entrada", help="arquivo com os processos (ex.: input/exemplo.txt)")
    parser.add_argument("--saida", help="salva a saída também em arquivo (ex.: output/resultado.txt)")
    parser.add_argument("--sem-filas", action="store_true",
                        help="não imprime o estado das filas a cada evento")
    args = parser.parse_args()

    if args.quantum < 1:
        parser.error("o quantum deve ser >= 1")
    if not 1 <= args.processos <= MAX_PROCESSOS:
        parser.error(f"a quantidade de processos deve estar entre 1 e {MAX_PROCESSOS}")

    if args.entrada:
        try:
            processos = ler_processos(args.entrada)
        except (OSError, ValueError) as erro:
            parser.error(f"erro ao ler '{args.entrada}': {erro}")
        origem = f"arquivo {args.entrada}"
    else:
        rng = random.Random(args.seed)
        processos = gerar_processos(args.processos, rng)
        origem = f"aleatório (seed={args.seed})"

    escrever("=" * 78)
    escrever("SIMULADOR DE ESCALONAMENTO - ROUND ROBIN COM FEEDBACK")
    escrever("=" * 78)
    escrever(f"[config] quantum={args.quantum} | processos={len(processos)} | origem={origem}")
    escrever(f"[config] I/O: " + "  ".join(
        f"{d}={DURACAO_IO[d]} u.t. (volta p/ {RETORNO_IO[d]})" for d in DISPOSITIVOS))
    escrever()
    imprimir_tabela_inicial(processos)
    escrever("Linha do tempo dos eventos:")

    resultado = simular(processos, args.quantum, mostrar_filas=not args.sem_filas)
    imprimir_resumo(processos, args.quantum, resultado)

    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as arq:
            arq.write("\n".join(_linhas_saida) + "\n")
        print(f"\nSaída salva em {args.saida}")


if __name__ == "__main__":
    main()
