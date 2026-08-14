import multiprocessing

_PREFERRED_PROVIDERS = [
    'CUDAExecutionProvider',
    'MIGraphXExecutionProvider',
    'ROCMExecutionProvider',
    'DmlExecutionProvider',
    'CoreMLExecutionProvider',
    'CPUExecutionProvider',
]


def _pick_providers():
    import onnxruntime as ort
    available = ort.get_available_providers()
    return [p for p in _PREFERRED_PROVIDERS if p in available] or ["CPUExecutionProvider"]


def serve(request_q, response_q, model_path):
    """Child-process entry: owns the ONNX session and serves inference requests.

    Creating an InferenceSession holds the Python GIL for its whole duration
    (measured ~8s for LaMa on CPU, longer on slow machines), which freezes the
    UI thread even when called from a QThread. Running it in a separate process
    keeps the app responsive regardless of how long loading takes.
    """
    try:
        import onnxruntime as ort
        session = ort.InferenceSession(model_path, providers=_pick_providers())
        input_names = [inp.name for inp in session.get_inputs()]
        response_q.put({"type": "ready", "input_names": input_names, "providers": session.get_providers()})
    except Exception as e:
        response_q.put({"type": "error", "message": str(e)})
        return

    while True:
        try:
            req = request_q.get()
        except (EOFError, OSError):
            return
        if req is None:
            return
        msg_type = req.get("type")
        if msg_type == "quit":
            return
        if msg_type == "infer":
            uid = req.get("uid")
            try:
                outputs = session.run(None, req["inputs"])
                response_q.put({"type": "result", "uid": uid, "data": outputs})
            except Exception as e:
                response_q.put({"type": "error", "uid": uid, "message": str(e)})


class OnnxModelProxy:
    """Main-process handle to an ONNX model running in a child process."""

    def __init__(self, model_path):
        ctx = multiprocessing.get_context("spawn")
        self._ctx = ctx
        self._request_q = ctx.Queue(maxsize=16)
        self._response_q = ctx.Queue(maxsize=16)
        self._proc = ctx.Process(
            target=serve,
            args=(self._request_q, self._response_q, model_path),
            daemon=True,
        )
        self._proc.start()
        self._uid = 0
        self._buffered = []
        self._closed = False
        ready = self._wait_ready()
        self.input_names = ready.get("input_names", [])
        self.providers = ready.get("providers", [])

    def _wait_ready(self):
        while True:
            try:
                msg = self._response_q.get(timeout=0.5)
            except Exception:
                msg = None
            if msg is None:
                if not self._proc.is_alive():
                    self._cleanup_proc()
                    raise RuntimeError("Model service process died during startup")
                continue
            if msg.get("type") == "ready":
                return msg
            if msg.get("type") == "error":
                self._cleanup_proc()
                raise RuntimeError(f"Model service failed: {msg.get('message')}")

    def run(self, inputs):
        if self._closed:
            raise RuntimeError("Model service is closed")
        self._uid += 1
        uid = self._uid
        self._request_q.put({"type": "infer", "uid": uid, "inputs": inputs})
        while True:
            for i, msg in enumerate(self._buffered):
                if msg.get("uid") == uid:
                    self._buffered.pop(i)
                    return self._handle_reply(msg)
            try:
                msg = self._response_q.get(timeout=0.5)
            except Exception:
                msg = None
            if msg is None:
                if not self._proc.is_alive():
                    raise RuntimeError("Model service process died during inference")
                continue
            if msg.get("uid") == uid:
                return self._handle_reply(msg)
            self._buffered.append(msg)

    def _handle_reply(self, msg):
        if msg.get("type") == "error":
            raise RuntimeError(f"Model inference failed: {msg.get('message')}")
        return msg.get("data")

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._request_q.put({"type": "quit"})
        except Exception:
            pass
        self._cleanup_proc()

    def _cleanup_proc(self):
        if self._proc is None:
            return
        self._proc.join(timeout=5)
        if self._proc.is_alive():
            self._proc.terminate()
            self._proc.join(timeout=5)
        try:
            self._request_q.close()
            self._response_q.close()
        except Exception:
            pass

    def __del__(self):
        try:
            if self._proc is not None and self._proc.is_alive():
                self._proc.terminate()
                self._proc.join(timeout=2)
        except Exception:
            pass