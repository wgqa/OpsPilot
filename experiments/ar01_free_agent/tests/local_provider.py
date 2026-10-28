"""Deterministic OpenAI-shaped loopback HTTP fixture; never a vendor emulator claim."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from experiments.ar01_free_agent.simulation import reactive


def messages(body):
    result=[]
    call_names={c["id"]:c["function"]["name"] for m in body["messages"] for c in m.get("tool_calls",[])}
    for m in body["messages"]:
        role,content=m["role"],m.get("content") or ""
        if role=="user": result.append(HumanMessage(content=content))
        elif role=="system": result.append(SystemMessage(content=content))
        elif role=="tool": result.append(ToolMessage(content=content,tool_call_id=m["tool_call_id"],
            name=m.get("name") or call_names.get(m["tool_call_id"])))
        else:
            result.append(AIMessage(content=content,tool_calls=[{"id":t["id"],"name":t["function"]["name"],
                "args":json.loads(t["function"]["arguments"])} for t in m.get("tool_calls",[])]))
    return result


@contextmanager
def provider(mode="normal"):
    state={"requests":[],"mode":mode,"errors":[],"release":threading.Event()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append(body)
            index=len(state["requests"])
            if state["mode"]=="wait": state["release"].wait(timeout=3)
            if state["mode"]=="lost":
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            if state["mode"]=="400":
                self.send_response(400)
                self.send_header("Content-Type","application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error":{"message":"unsupported parameter","type":"invalid_request_error"}}).encode())
                return
            ai=reactive(messages(body))
            msg={"role":"assistant","content":ai.content}
            if ai.tool_calls:
                msg["tool_calls"]=[{"id":c["id"],"type":"function","function":{"name":c["name"],
                    "arguments":json.dumps(c["args"],ensure_ascii=False)}} for c in ai.tool_calls]
            response={"id":f"local-completion-{index}","object":"chat.completion","created":1,
                "model":"deepseek-flash","system_fingerprint":"local-stub-v1",
                "choices":[{"index":0,"finish_reason":"tool_calls" if ai.tool_calls else "stop","message":msg}],
                "usage":{"prompt_tokens":100,"completion_tokens":20,"total_tokens":120,
                    "prompt_cache_hit_tokens":0,"prompt_cache_miss_tokens":100}}
            if state["mode"]=="missing-usage": response.pop("usage")
            if state["mode"]=="extra-output": response["usage"].update(completion_tokens=600,total_tokens=700)
            if state["mode"]=="drift" and index>1: response["system_fingerprint"]="different-stub"
            if state["mode"]=="missing-id": response.pop("system_fingerprint")
            if state["mode"]=="no-completion": response.pop("id")
            if state["mode"]=="no-finish": response["choices"][0].pop("finish_reason")
            if state["mode"]=="input-overrun": response["usage"].update(prompt_tokens=1_048_577,total_tokens=1_048_597,prompt_cache_miss_tokens=1_048_577)
            if state["mode"]=="both-bound-overrun": response["usage"].update(prompt_tokens=1_048_576,completion_tokens=393216,total_tokens=1_441_792,prompt_cache_miss_tokens=1_048_576)
            if state["mode"]=="reasoning": response["usage"]["completion_tokens_details"]={"reasoning_tokens":5}
            if state["mode"]=="reasoning-text": response["choices"][0]["message"]["reasoning_content"]="test hidden reasoning, never persist"
            if state["mode"]=="bad-total": response["usage"]["total_tokens"]=1
            value=json.dumps(response,ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(value)))
            if state["mode"]!="no-request-id": self.send_header("x-request-id",f"local-http-request-{index}")
            self.end_headers()
            try: self.wfile.write(value)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    state["url"]=f"http://127.0.0.1:{server.server_port}"
    try: yield state
    finally:
        state["release"].set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
