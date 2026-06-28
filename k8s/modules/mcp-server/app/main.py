import asyncio
import json
import os
from datetime import datetime, timedelta

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

OPENSEARCH_URL = os.environ["OPENSEARCH_URL"]
OPENSEARCH_INDEX_LOGS = os.getenv("OPENSEARCH_INDEX_LOGS", "logs-app-*")
OPENSEARCH_INDEX_TRACES = os.getenv("OPENSEARCH_INDEX_TRACES", "traces-*")

app = Server("opensearch-mcp")


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=OPENSEARCH_URL,
        timeout=30,
        verify=True,
    )


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_logs",
            description=(
                "Logok keresése az OpenSearch-ben. Szűrhető namespace, pod, log level "
                "és időintervallum alapján. Visszaadja a találatokat szövegesen."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Szabad szöveges keresési kifejezés",
                    },
                    "level": {
                        "type": "string",
                        "enum": ["ERROR", "WARN", "INFO", "DEBUG"],
                        "description": "Log szint szűrő (opcionális)",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace (opcionális, pl. java-app-prod)",
                    },
                    "minutes_ago": {
                        "type": "integer",
                        "description": "Az elmúlt N perc logjai (alapértelmezett: 60)",
                        "default": 60,
                    },
                    "size": {
                        "type": "integer",
                        "description": "Maximális találatszám (alapértelmezett: 50)",
                        "default": 50,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_error_summary",
            description=(
                "Az elmúlt időszak ERROR logjainak összesítése – darabszám és mintaüzenetek "
                "per pod/deployment. Gyors hibaáttekintéshez."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace",
                        "default": "java-app-prod",
                    },
                    "hours_ago": {
                        "type": "integer",
                        "description": "Visszatekintési időablak órában (alapértelmezett: 24)",
                        "default": 24,
                    },
                },
            },
        ),
        Tool(
            name="get_trace",
            description="Egy konkrét trace részleteinek lekérdezése trace ID alapján.",
            inputSchema={
                "type": "object",
                "properties": {
                    "trace_id": {
                        "type": "string",
                        "description": "OpenTelemetry trace ID (hex formátum)",
                    },
                },
                "required": ["trace_id"],
            },
        ),
        Tool(
            name="get_slow_queries",
            description=(
                "A leglassabb PostgreSQL lekérdezések listája az OpenSearch-be exportált "
                "pg_stat_statements adatok alapján."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "Top N lekérdezés (alapértelmezett: 10)",
                        "default": 10,
                    },
                    "hours_ago": {
                        "type": "integer",
                        "default": 24,
                    },
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    async with _http_client() as client:
        if name == "search_logs":
            result = await _search_logs(client, arguments)
        elif name == "get_error_summary":
            result = await _get_error_summary(client, arguments)
        elif name == "get_trace":
            result = await _get_trace(client, arguments)
        elif name == "get_slow_queries":
            result = await _get_slow_queries(client, arguments)
        else:
            result = f"Ismeretlen tool: {name}"

    return [TextContent(type="text", text=result)]


async def _search_logs(client: httpx.AsyncClient, args: dict) -> str:
    minutes_ago = args.get("minutes_ago", 60)
    size = min(args.get("size", 50), 200)
    since = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat() + "Z"

    must = [
        {"range": {"@timestamp": {"gte": since}}},
        {"query_string": {"query": args["query"], "default_field": "body"}},
    ]

    if level := args.get("level"):
        must.append({"term": {"attributes.level": level}})

    if ns := args.get("namespace"):
        must.append({"term": {"resource.k8s.namespace.name": ns}})

    payload = {
        "size": size,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "query": {"bool": {"must": must}},
        "_source": ["@timestamp", "body", "attributes.level", "resource.k8s.pod.name",
                    "resource.k8s.namespace.name", "attributes.traceId"],
    }

    resp = await client.post(f"/{OPENSEARCH_INDEX_LOGS}/_search", json=payload)
    resp.raise_for_status()
    hits = resp.json()["hits"]["hits"]

    if not hits:
        return "Nincs találat a megadott feltételekre."

    lines = []
    for h in hits:
        src = h["_source"]
        ts = src.get("@timestamp", "")
        level_str = src.get("attributes", {}).get("level", "")
        pod = src.get("resource", {}).get("k8s.pod.name", "")
        body = src.get("body", "")
        trace_id = src.get("attributes", {}).get("traceId", "")
        trace_suffix = f" [trace={trace_id[:8]}...]" if trace_id else ""
        lines.append(f"[{ts}] {level_str} {pod}: {body}{trace_suffix}")

    return f"Találatok ({len(hits)}):\n\n" + "\n".join(lines)


async def _get_error_summary(client: httpx.AsyncClient, args: dict) -> str:
    ns = args.get("namespace", "java-app-prod")
    hours_ago = args.get("hours_ago", 24)
    since = (datetime.utcnow() - timedelta(hours=hours_ago)).isoformat() + "Z"

    payload = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"term": {"attributes.level": "ERROR"}},
                    {"term": {"resource.k8s.namespace.name": ns}},
                    {"range": {"@timestamp": {"gte": since}}},
                ]
            }
        },
        "aggs": {
            "by_pod": {
                "terms": {"field": "resource.k8s.pod.name", "size": 20},
                "aggs": {
                    "sample_messages": {
                        "terms": {"field": "body.keyword", "size": 3}
                    }
                },
            }
        },
    }

    resp = await client.post(f"/{OPENSEARCH_INDEX_LOGS}/_search", json=payload)
    resp.raise_for_status()
    data = resp.json()

    total = data["hits"]["total"]["value"]
    buckets = data["aggregations"]["by_pod"]["buckets"]

    if not buckets:
        return f"Nincs ERROR log a {ns} namespaceben az elmúlt {hours_ago} órában."

    lines = [f"ERROR összesítő – {ns} – elmúlt {hours_ago} óra – összesen: {total}\n"]
    for b in buckets:
        pod = b["key"]
        count = b["doc_count"]
        samples = [s["key"] for s in b["sample_messages"]["buckets"]]
        lines.append(f"  {pod}: {count} error")
        for s in samples:
            lines.append(f"    - {s[:120]}")

    return "\n".join(lines)


async def _get_trace(client: httpx.AsyncClient, args: dict) -> str:
    trace_id = args["trace_id"]

    payload = {
        "size": 100,
        "sort": [{"startTime": {"order": "asc"}}],
        "query": {"term": {"traceId": trace_id}},
        "_source": ["spanId", "parentSpanId", "name", "serviceName",
                    "startTime", "endTime", "status.code", "attributes"],
    }

    resp = await client.post(f"/{OPENSEARCH_INDEX_TRACES}/_search", json=payload)
    resp.raise_for_status()
    hits = resp.json()["hits"]["hits"]

    if not hits:
        return f"Nem található trace: {trace_id}"

    lines = [f"Trace: {trace_id} ({len(hits)} span)\n"]
    for h in hits:
        src = h["_source"]
        duration_ms = (src.get("endTime", 0) - src.get("startTime", 0)) / 1_000_000
        status = src.get("status", {}).get("code", "OK")
        lines.append(
            f"  [{src.get('serviceName', '')}] {src.get('name', '')} "
            f"– {duration_ms:.1f}ms – {status}"
        )

    return "\n".join(lines)


async def _get_slow_queries(client: httpx.AsyncClient, args: dict) -> str:
    top_n = args.get("top_n", 10)
    hours_ago = args.get("hours_ago", 24)
    since = (datetime.utcnow() - timedelta(hours=hours_ago)).isoformat() + "Z"

    payload = {
        "size": top_n,
        "sort": [{"mean_exec_time": {"order": "desc"}}],
        "query": {
            "bool": {
                "must": [
                    {"term": {"type": "pg_stat_statements"}},
                    {"range": {"@timestamp": {"gte": since}}},
                ]
            }
        },
        "_source": ["query", "mean_exec_time", "calls", "total_exec_time"],
    }

    resp = await client.post(f"/logs-db-*/_search", json=payload)
    resp.raise_for_status()
    hits = resp.json()["hits"]["hits"]

    if not hits:
        return "Nincs adat (a pg_stat_statements export fut?)"

    lines = [f"Top {top_n} leglassabb PG lekérdezés (elmúlt {hours_ago} óra):\n"]
    for i, h in enumerate(hits, 1):
        src = h["_source"]
        q = src.get("query", "").replace("\n", " ")[:100]
        mean = src.get("mean_exec_time", 0)
        calls = src.get("calls", 0)
        lines.append(f"{i}. avg={mean:.1f}ms calls={calls}\n   {q}")

    return "\n".join(lines)


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
