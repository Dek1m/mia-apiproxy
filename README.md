# API Proxy Module for Mia Framework

Прослойка между CLI/REST и модулями (auth, workspace, llm).

## Features

- **MethodRegistry** — сбор и хранение метаданных API-методов
- **AuthMiddleware** — проверка авторизации (token → permissions)
- **Converter** — валидация аргументов, вызов, нормализация ответа
- **Whitelist** — контроль доступных модулей

## Architecture

```
CLI/REST → ApiProxyProvider.call() → AuthMiddleware → MethodRegistry → func()
```

## Installation

```bash
git clone https://github.com/Dek1m/mia-apiproxy.git
cd mia-apiproxy
pip install -e .
```

## Configuration

| Env Variable | Default | Description |
|---|---|---|
| `MIA_APIPROXY_WHITELIST` | `auth,workspace,llm` | Whitelist модулей |
| `MIA_APIPROXY_METHOD_TIMEOUT` | `30.0` | Таймаут метода |

## License

MIT
