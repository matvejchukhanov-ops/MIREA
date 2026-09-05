# Диаграммы

Все диаграммы записаны на языке Mermaid и отрисовываются GitHub автоматически —
исходный текст остаётся в репозитории и правится вместе с кодом.

---

## 1. Диаграмма компонентов

Показывает, из каких частей состоит система и в какую сторону направлены
зависимости.

```mermaid
graph TB
    subgraph CL["Клиент"]
        CM["main.py<br/>цикл ввода, разбор команд"]
        CC["connection.py<br/>ServerConnection"]
    end

    subgraph CO["common — общий код"]
        FR["framing.py<br/>FrameReader, encode_frame"]
    end

    subgraph SV["Сервер"]
        SM["main.py<br/>аргументы, точка входа"]
        TS["tcp_server.py<br/>TCPServer"]
        CN["connection.py<br/>обмен с клиентом"]
        PR["protocol.py<br/>Request, ErrorCode"]
        DP["dispatcher.py<br/>Dispatcher"]
        HD["handlers.py<br/>calc, ping, history, quit"]
        SS["session.py<br/>Session"]
        CF["config.py<br/>ServerConfig"]
    end

    subgraph CA["server/calc — вычислительное ядро"]
        LX["lexer.py"]
        PS["parser.py"]
        EV["evaluator.py"]
        ER["errors.py"]
    end

    CM --> CC
    CC --> FR
    CC -. "TCP :9000" .-> CN

    SM --> TS
    SM --> CF
    TS --> CN
    TS --> DP
    CN --> FR
    CN --> PR
    CN --> SS
    DP --> HD
    HD --> CA
    LX --> ER
    PS --> LX
    EV --> PS
```

Обрати внимание на два обстоятельства:

- **`common/framing.py` используют обе стороны.** Проблема границ сообщений
  симметрична, дублировать код означало бы чинить каждую ошибку дважды.
- **`server/calc/` не имеет ни одной стрелки в сторону сети.** Это позволяет
  тестировать вычисления без сокетов.

---

## 2. Диаграмма классов: сетевая часть

```mermaid
classDiagram
    class TCPServer {
        -ServerConfig _config
        -Dispatcher _dispatcher
        -Lock _lock
        -int _active
        +serve_forever()
        +shutdown()
        +active_connections() int
    }

    class ServerConfig {
        +str host
        +int port
        +int backlog
        +int recv_size
        +int max_frame_size
        +float idle_timeout
        +int max_connections
        +from_env() ServerConfig
    }

    class Dispatcher {
        -dict _handlers
        +register(name, handler)
        +dispatch(request, session)
        +commands() list
    }

    class Session {
        +str peer
        +bool should_close
        +deque history
        +remember(expr, result)
        +recent(limit) list
    }

    class Request {
        +str cmd
        +id
        +dict payload
        +require_str(name) str
        +optional_int(name, default) int
    }

    class FrameReader {
        -bytearray _buffer
        -int _max_frame_size
        +feed(data) list
        +pending() int
        +reset()
    }

    class ProtocolError {
        +ErrorCode code
        +str message
        +int position
    }

    TCPServer --> ServerConfig : читает
    TCPServer --> Dispatcher : владеет
    TCPServer ..> Session : создаёт на клиента
    TCPServer ..> FrameReader : создаёт на клиента
    Dispatcher ..> Request : принимает
    Dispatcher ..> Session : передаёт обработчику
    Dispatcher ..> ProtocolError : бросает
```

`Dispatcher` один на весь сервер и после сборки только читается, поэтому
делится между потоками без синхронизации. `Session` и `FrameReader` создаются
на каждое соединение и живут внутри своего потока.

---

## 3. Диаграмма классов: дерево разбора

```mermaid
classDiagram
    class Node {
        <<union>>
    }
    class Number {
        +value
        +int position
    }
    class UnaryOp {
        +str operator
        +Node operand
        +int position
    }
    class BinaryOp {
        +str operator
        +Node left
        +Node right
        +int position
    }
    class Token {
        +TokenType type
        +int position
        +value
    }

    Node <|-- Number
    Node <|-- UnaryOp
    Node <|-- BinaryOp
    UnaryOp --> Node : operand
    BinaryOp --> Node : left, right
```

Уточнение: в коде `Node` — не базовый класс, а объединение типов
(`Number | UnaryOp | BinaryOp`). На диаграмме показано наследованием, потому
что смысл тот же: в любом месте, где ожидается узел, допустим любой из трёх.

---

## 4. Диаграмма последовательности: вычисление выражения

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant C as Клиент
    participant T as TCPServer
    participant N as connection
    participant P as protocol
    participant D as Dispatcher
    participant H as handle_calc
    participant K as calc

    U->>C: вводит "2 + 3 * 4"
    C->>C: build_request
    C->>N: кадр запроса по TCP

    Note over T,N: соединение уже принято,<br/>обмен идёт в своём потоке

    N->>N: FrameReader.feed
    N->>P: parse_request
    P-->>N: Request
    N->>D: dispatch
    D->>H: handle_calc
    H->>K: calculate
    K->>K: tokenize
    K->>K: parse
    K->>K: evaluate
    K-->>H: 14
    H->>H: session.remember
    H-->>D: 14
    D-->>N: 14
    N->>P: success_frame
    P-->>N: кадр ответа
    N-->>C: кадр ответа по TCP
    C->>C: format_response
    C-->>U: 14
```

---

## 5. Диаграмма последовательности: ошибка вычисления

Показывает, что ошибка в данных клиента **не разрывает соединение**.

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant C as Клиент
    participant N as connection
    participant D as Dispatcher
    participant H as handle_calc
    participant K as calc

    U->>C: вводит "10 / 0"
    C->>N: кадр запроса
    N->>D: dispatch
    D->>H: handle_calc
    H->>K: calculate
    K--xH: DivisionByZeroError
    H--xD: ProtocolError DIV_BY_ZERO
    D--xN: ProtocolError
    N->>N: error_frame
    N-->>C: status error, code DIV_BY_ZERO
    C-->>U: Ошибка [DIV_BY_ZERO]

    Note over N: соединение остаётся открытым

    U->>C: вводит "2 + 2"
    C->>N: кадр запроса
    N-->>C: status ok, result 4
    C-->>U: 4
```

---

## 6. Диаграмма состояний соединения

```mermaid
stateDiagram-v2
    state "Ожидание данных" as reading
    state "Сборка кадра" as framing
    state "Обработка запроса" as processing
    state "Корректное закрытие" as closing

    [*] --> reading : accept, запуск потока
    reading --> framing : recv вернул байты
    framing --> reading : кадр не завершён
    framing --> processing : кадр собран
    processing --> reading : ответ отправлен
    processing --> closing : команда quit
    reading --> closing : recv вернул 0
    reading --> closing : таймаут бездействия
    framing --> closing : превышен размер кадра
    closing --> [*] : сокет закрыт, поток завершён
```

Переход `framing → reading` — тот самый случай, когда сообщение пришло не
целиком: часть байт остаётся в буфере до следующего чтения.

---

## 7. Диаграмма деятельности: обработка одного кадра

```mermaid
flowchart TD
    A["Кадр получен"] --> B{"Разбирается<br/>как JSON?"}
    B -- нет --> E1["Ответ BAD_JSON"]
    B -- да --> C{"Это объект<br/>с полем cmd?"}
    C -- нет --> E2["Ответ BAD_REQUEST"]
    C -- да --> D{"Команда<br/>известна?"}
    D -- нет --> E3["Ответ UNKNOWN_COMMAND"]
    D -- да --> F["Вызов обработчика"]
    F --> G{"Результат?"}
    G -- "ProtocolError" --> E4["Ответ с кодом ошибки"]
    G -- "прочее исключение" --> E5["Лог с трассировкой<br/>Ответ INTERNAL_ERROR"]
    G -- "значение" --> H["Ответ status ok"]

    E1 --> Z["Отправка кадра ответа"]
    E2 --> Z
    E3 --> Z
    E4 --> Z
    E5 --> Z
    H --> Z
    Z --> Y["Соединение остаётся открытым"]
```

Ключевое свойство: **из этой схемы нет выхода в разрыв соединения.** Любая
беда становится ответом. Соединение закрывается только выше по уровню —
при нарушении фрейминга или по команде `quit`.

---

## 8. Диаграмма потоков сервера

```mermaid
graph TB
    M["Главный поток<br/>цикл accept()"]
    L{"Достигнут предел<br/>подключений?"}
    R["refuse_connection<br/>SERVER_BUSY"]
    T1["Поток client-1<br/>Session, FrameReader"]
    T2["Поток client-2<br/>Session, FrameReader"]
    T3["Поток client-N<br/>Session, FrameReader"]
    S["Общее состояние:<br/>счётчик подключений<br/>под threading.Lock"]
    DP["Dispatcher<br/>только чтение"]

    M --> L
    L -- да --> R
    L -- нет --> T1
    L -- нет --> T2
    L -- нет --> T3
    T1 -.-> S
    T2 -.-> S
    T3 -.-> S
    M -.-> S
    T1 -.-> DP
    T2 -.-> DP
    T3 -.-> DP
```

Общего изменяемого состояния всего одно — счётчик. Буфер чтения и история
живут внутри своего потока, поэтому гонкам взяться неоткуда. Это не
случайность, а способ проектирования: надёжнее устранить условия для гонок,
чем расставлять блокировки.

---

## 9. Диаграмма развёртывания

```mermaid
graph LR
    subgraph H["Рабочая станция"]
        subgraph P1["Процесс: сервер"]
            SRV["python -m server.main<br/>слушает 127.0.0.1:9000"]
        end
        subgraph P2["Процесс: клиент 1"]
            CL1["python -m client.main"]
        end
        subgraph P3["Процесс: клиент N"]
            CL2["python -m client.main"]
        end
    end

    CL1 -- "TCP" --> SRV
    CL2 -- "TCP" --> SRV
```

Штатный режим — всё на одной машине через петлевой интерфейс. Для работы по
локальной сети сервер запускается с `--host 0.0.0.0`, клиент получает адрес
машины через `--host`. Шифрования нет, поэтому выставлять сервер в интернет
не следует.

---

## 10. Дерево разбора выражения

Наглядное объяснение того, откуда берётся приоритет операций.

Выражение `2 + 3 * 4`:

```mermaid
graph TD
    A(("+")) --- B(("2"))
    A --- C(("*"))
    C --- D(("3"))
    C --- E(("4"))
```

Умножение оказалось **глубже** в дереве, а вычисление идёт снизу вверх:
сначала `3 * 4 = 12`, потом `2 + 12 = 14`. Приоритет нигде не запрограммирован —
он следует из того, что правило «выражение» состоит из «слагаемых», а
«слагаемое» из «множителей».

Для сравнения, `(2 + 3) * 4`:

```mermaid
graph TD
    A(("*")) --- B(("+"))
    A --- C(("4"))
    B --- D(("2"))
    B --- E(("3"))
```

Скобки подняли сложение вниз по дереву, и оно вычисляется первым: `20`.
