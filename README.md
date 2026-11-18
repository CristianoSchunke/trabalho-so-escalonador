# Trabalho Final de Sistemas Operacionais

Simulador de escalonamento de processos **Round Robin com Feedback**, com filas de
alta e baixa prioridade e tratamento de I/O (disco, fita magnética e impressora).

## Grupo
- Jean Lucas Bremm Machado
- Matheus Reinehr Stoffel

## Linguagem utilizada
Python 3 (testado com Python 3.12). Usa apenas a biblioteca padrão, sem dependências externas.

Seguindo a restrição do trabalho, o simulador **não usa orientação a objetos**: o PCB é
um dicionário, as filas são `collections.deque` (FIFO) e toda a lógica está em funções.

## Estrutura do repositório
```
├── src/
│   └── escalonador.py     # simulador completo
├── input/
│   └── exemplo.txt        # exemplo de entrada por arquivo
├── output/                # saídas geradas com --saida (opcional)
├── Dockerfile             # bônus Docker
├── .dockerignore
└── README.md
```

## Premissas do escalonador
| Premissa | Valor adotado |
|---|---|
| Quantum | 3 u.t. (alterável com `--quantum`) |
| Número de processos | 6 por padrão; máximo de 20 (`--processos`) |
| Tempo de CPU de cada processo | aleatório entre 4 e 12 u.t. |
| Instante de chegada | aleatório entre t=0 e t=10 (o P1 sempre chega em t=0) |
| Operações de I/O por processo | de 0 a 2, em instantes aleatórios da execução de CPU |
| Duração do I/O | DISCO = 3 u.t., FITA = 5 u.t., IMPRESSORA = 8 u.t. |
| Retorno do I/O | DISCO → fila BAIXA; FITA → fila ALTA; IMPRESSORA → fila ALTA |
| PPID | P1 é filho do sistema (PPID 0); os demais são filhos do sistema (40%) ou de um processo criado antes |
| Critério de criação | processos gerados aleatoriamente pela semente **ou** lidos de arquivo (`--entrada`) |
| Semente aleatória | 42 por padrão (`--seed`); a semente usada é impressa na saída |
| Fim da simulação | quando todos os processos estão FINALIZADOS |

Regras do algoritmo:
- Processo novo entra na fila **ALTA**.
- A CPU sempre escolhe primeiro a fila ALTA; a BAIXA só é usada se a ALTA estiver vazia.
- Processo que usa o quantum inteiro sem terminar sofre **preempção** e vai para a fila **BAIXA**.
- Processo que pede I/O fica **BLOQUEADO** na fila do dispositivo. Cada dispositivo atende
  um processo por vez (FIFO); ao terminar, o processo volta para a fila definida acima.
- Não há preempção por prioridade: um processo da fila BAIXA que está na CPU termina sua
  fatia mesmo que chegue alguém na fila ALTA.
- Quando vários eventos acontecem no mesmo instante, a ordem é: chegadas → retornos de I/O →
  processo que saiu da CPU (fim / I/O / preempção) → início de I/O → escolha do próximo processo.

## Como executar o projeto
```bash
# Execução tradicional (Python 3)
python src/escalonador.py

# Outras opções
python src/escalonador.py --seed 7 --processos 8      # outra semente e quantidade
python src/escalonador.py --quantum 4                 # outro quantum
python src/escalonador.py --entrada input/exemplo.txt # processos lidos de arquivo
python src/escalonador.py --saida output/resultado.txt # também salva a saída em arquivo
python src/escalonador.py --sem-filas                 # log mais curto, sem o estado das filas
python src/escalonador.py --help
```
> No Windows, se `python` não for reconhecido, use `py src/escalonador.py`.

### Bônus Docker
```bash
# Construir a imagem
docker build -t so-escalonador .

# Executar o simulador
docker run --rm so-escalonador

# Passando opções (tudo depois do nome da imagem vai para o simulador)
docker run --rm so-escalonador --entrada input/exemplo.txt --quantum 4
```
Salvando a saída em arquivo na pasta `output/` do seu computador:
```bash
# Linux/macOS
docker run --rm -v "$(pwd)/output:/app/output" so-escalonador --saida output/resultado.txt

# Windows PowerShell
docker run --rm -v "${PWD}/output:/app/output" so-escalonador --saida output/resultado.txt
```

### Formato do arquivo de entrada
```
# PID PPID CHEGADA TEMPO_CPU [instante:DISPOSITIVO ...]
1 0 0 8 2:DISCO
3 1 2 7 3:FITA
```
`instante` é quantas unidades de CPU o processo já executou quando pede o I/O
(ex.: `2:DISCO` = depois de usar 2 u.t. de CPU, pede o disco).

## O que aparece na saída
1. **Configuração**: quantum, número de processos, origem (semente ou arquivo) e duração de cada I/O.
2. **PCB inicial**: tabela com PID, PPID, chegada, tempo de CPU, status, prioridade e I/Os previstos.
3. **Linha do tempo dos eventos**: cada linha começa com `[t=XXX]` e mostra um evento:
   - `P3 criado ... -> fila ALTA` — chegada de processo;
   - `CPU executa P1 (veio da fila BAIXA, restante=6) por até 3 u.t. [quantum]` — despacho;
   - `P2 sofreu preempção (fim do quantum, faltam 2) -> fila BAIXA` — feedback para a fila baixa;
   - `P1 solicitou I/O DISCO por 3 u.t. -> BLOQUEADO` e `DISCO inicia atendimento de P1`;
   - `P3 retornou da FITA -> fila ALTA` — retorno de I/O;
   - `P4 FINALIZADO (turnaround = 16 u.t.)` e `CPU ociosa`.

   Abaixo dos eventos, uma linha mostra o estado de todas as filas naquele instante, por exemplo:
   `CPU=P3  ALTA=[P4]  BAIXA=[P1,P2]  DISCO=[]  FITA=[P5*]  IMPRESSORA=[]`
   (o `*` marca o processo que está sendo atendido pelo dispositivo).
4. **Resumo final**: diagrama de Gantt da CPU, tabela por processo (início, fim, turnaround,
   espera, resposta, preempções) e métricas gerais: tempo total, trocas de contexto, preempções,
   eventos de I/O por tipo, tempos médios de espera/turnaround/resposta e % de CPU ociosa.

Trecho da execução com `input/exemplo.txt`:
```
[t=002] P1 solicitou I/O DISCO por 3 u.t. -> BLOQUEADO
[t=002] DISCO inicia atendimento de P1 (termina em t=5)
[t=002] CPU executa P2 (veio da fila ALTA, restante=5) por até 3 u.t. [quantum]
         CPU=P2  ALTA=[P3]  BAIXA=[]  DISCO=[P1*]  FITA=[]  IMPRESSORA=[]
[t=005] P1 retornou do DISCO -> fila BAIXA
[t=005] P2 sofreu preempção (fim do quantum, faltam 2) -> fila BAIXA
```

## Limitações conhecidas
- A simulação é em tempo discreto (unidades inteiras); não há custo de troca de contexto.
- Só existe uma CPU.
- Não há preempção por prioridade nem envelhecimento (*aging*): processos na fila BAIXA podem
  esperar bastante se sempre houver processos na fila ALTA.
- O PPID é apenas informativo: não há criação dinâmica de processos filhos durante a simulação.
- A duração de cada dispositivo de I/O é fixa.
