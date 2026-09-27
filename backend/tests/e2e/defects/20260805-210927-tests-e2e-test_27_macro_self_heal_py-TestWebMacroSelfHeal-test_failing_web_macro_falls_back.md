# E2E 缺陷报告：test_failing_web_macro_falls_back

- **测试 ID**: `tests/e2e/test_27_macro_self_heal.py::TestWebMacroSelfHeal::test_failing_web_macro_falls_back`
- **发现时间**: 2026-08-05T21:09:27.526428
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
@contextlib.contextmanager
    def map_httpcore_exceptions() -> typing.Iterator[None]:
        global HTTPCORE_EXC_MAP
        if len(HTTPCORE_EXC_MAP) == 0:
            HTTPCORE_EXC_MAP = _load_httpcore_exceptions()
        try:
>           yield

.venv/lib/python3.11/site-packages/httpx/_transports/default.py:101: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <httpx.AsyncHTTPTransport object at 0x1184f4c50>
request = <Request('POST', 'http://127.0.0.1:20160/api/v1/chat')>

    async def handle_async_request(
        self,
        request: Request,
    ) -> Response:
        assert isinstance(request.stream, AsyncByteStream)
        import httpcore
    
        req = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        with map_httpcore_exceptions():
>           resp = await self._pool.handle_async_request(req)

.venv/lib/python3.11/site-packages/httpx/_transports/default.py:394: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <AsyncHTTPProxy [Requests: 0 active, 0 queued | Connections: 0 active, 0 idle]>
request = <Request [b'POST']>

    async def handle_async_request(self, request: Request) -> Response:
        """
        Send an HTTP request, and return an HTTP response.
    
        This is the core implementation that is called into by `.request()` or `.stream()`.
        """
        scheme = request.url.scheme.decode()
        if scheme == "":
            raise UnsupportedProtocol(
                "Request URL is missing an 'http://' or 'https://' protocol."
            )
        if scheme not in ("http", "https", "ws", "wss"):
            raise UnsupportedProtocol(
                f"Request URL has an unsupported protocol '{scheme}://'."
            )
    
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("pool", None)
    
        with self._optional_thread_lock:
            # Add the incoming request to our request queue.
            pool_request = AsyncPoolRequest(request)
            self._requests.append(pool_request)
    
        try:
            while True:
                with self._optional_thread_lock:
                    # Assign incoming requests to available connections,
                    # closing or creating new connections as required.
                    closing = self._assign_requests_to_connections()
                await self._close_connections(closing)
    
                # Wait until this request has an assigned connection.
                connection = await pool_request.wait_for_connection(timeout=timeout)
    
                try:
                    # Send the request on the assigned connection.
                    response = await connection.handle_async_request(
                        pool_request.request
                    )
                except ConnectionNotAvailable:
                    # In some cases a connection may initially be available to
                    # handle a request, but then become unavailable.
                    #
                    # In this case we clear the connection and try again.
                    pool_request.clear_connection()
                else:
                    break  # pragma: nocover
    
        except BaseException as exc:
            with self._optional_thread_lock:
                # For any exception or cancellation we remove the request from
                # the queue, and then re-assign requests to connections.
                self._requests.remove(pool_request)
                closing = self._assign_requests_to_connections()
    
            await self._close_connections(closing)
>           raise exc from None

.venv/lib/python3.11/site-packages/httpcore/_async/connection_pool.py:256: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <AsyncHTTPProxy [Requests: 0 active, 0 queued | Connections: 0 active, 0 idle]>
request = <Request [b'POST']>

    async def handle_async_request(self, request: Request) -> Response:
        """
        Send an HTTP request, and return an HTTP response.
    
        This is the core implementation that is called into by `.request()` or `.stream()`.
        """
        scheme = request.url.scheme.decode()
        if scheme == "":
            raise UnsupportedProtocol(
                "Request URL is missing an 'http://' or 'https://' protocol."
            )
        if scheme not in ("http", "https", "ws", "wss"):
            raise UnsupportedProtocol(
                f"Request URL has an unsupported protocol '{scheme}://'."
            )
    
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("pool", None)
    
        with self._optional_thread_lock:
            # Add the incoming request to our request queue.
            pool_request = AsyncPoolRequest(request)
            self._requests.append(pool_request)
    
        try:
            while True:
                with self._optional_thread_lock:
                    # Assign incoming requests to available connections,
                    # closing or creating new connections as required.
                    closing = self._assign_requests_to_connections()
                await self._close_connections(closing)
    
                # Wait until this request has an assigned connection.
                connection = await pool_request.wait_for_connection(timeout=timeout)
    
                try:
                    # Send the request on the assigned connection.
>                   response = await connection.handle_async_request(
                        pool_request.request
                    )

.venv/lib/python3.11/site-packages/httpcore/_async/connection_pool.py:236: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <AsyncForwardHTTPConnection ['http://127.0.0.1:7897', HTTP/1.1, CLOSED, Request Count: 1]>
request = <Request [b'POST']>

    async def handle_async_request(self, request: Request) -> Response:
        headers = merge_headers(self._proxy_headers, request.headers)
        url = URL(
            scheme=self._proxy_origin.scheme,
            host=self._proxy_origin.host,
            port=self._proxy_origin.port,
            target=bytes(request.url),
        )
        proxy_request = Request(
            method=request.method,
            url=url,
            headers=headers,
            content=request.stream,
            extensions=request.extensions,
        )
>       return await self._connection.handle_async_request(proxy_request)

.venv/lib/python3.11/site-packages/httpcore/_async/http_proxy.py:206: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <AsyncHTTPConnection ['http://127.0.0.1:7897', HTTP/1.1, CLOSED, Request Count: 1]>
request = <Request [b'POST']>

    async def handle_async_request(self, request: Request) -> Response:
        if not self.can_handle_request(request.url.origin):
            raise RuntimeError(
                f"Attempted to send request to {request.url.origin} on connection to {self._origin}"
            )
    
        try:
            async with self._request_lock:
                if self._connection is None:
                    stream = await self._connect(request)
    
                    ssl_object = stream.get_extra_info("ssl_object")
                    http2_negotiated = (
                        ssl_object is not None
                        and ssl_object.selected_alpn_protocol() == "h2"
                    )
                    if http2_negotiated or (self._http2 and not self._http1):
                        from .http2 import AsyncHTTP2Connection
    
                        self._connection = AsyncHTTP2Connection(
                            origin=self._origin,
                            stream=stream,
                            keepalive_expiry=self._keepalive_expiry,
                        )
                    else:
                        self._connection = AsyncHTTP11Connection(
                            origin=self._origin,
                            stream=stream,
                            keepalive_expiry=self._keepalive_expiry,
                        )
        except BaseException as exc:
            self._connect_failed = True
            raise exc
    
>       return await self._connection.handle_async_request(request)

.venv/lib/python3.11/site-packages/httpcore/_async/connection.py:103: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <AsyncHTTP11Connection ['http://127.0.0.1:7897', CLOSED, Request Count: 1]>
request = <Request [b'POST']>

    async def handle_async_request(self, request: Request) -> Response:
        if not self.can_handle_request(request.url.origin):
            raise RuntimeError(
                f"Attempted to send request to {request.url.origin} on connection "
                f"to {self._origin}"
            )
    
        async with self._state_lock:
            if self._state in (HTTPConnectionState.NEW, HTTPConnectionState.IDLE):
                self._request_count += 1
                self._state = HTTPConnectionState.ACTIVE
                self._expire_at = None
            else:
                raise ConnectionNotAvailable()
    
        try:
            kwargs = {"request": request}
            try:
                async with Trace(
                    "send_request_headers", logger, request, kwargs
                ) as trace:
                    await self._send_request_headers(**kwargs)
                async with Trace("send_request_body", logger, request, kwargs) as trace:
                    await self._send_request_body(**kwargs)
            except WriteError:
                # If we get a write error while we're writing the request,
                # then we supress this error and move on to attempting to
                # read the response. Servers can sometimes close the request
                # pre-emptively and then respond with a well formed HTTP
                # error response.
                pass
    
            async with Trace(
                "receive_response_headers", logger, request, kwargs
            ) as trace:
                (
                    http_version,
                    status,
                    reason_phrase,
                    headers,
                    trailing_data,
                ) = await self._receive_response_headers(**kwargs)
                trace.return_value = (
                    http_version,
                    status,
                    reason_phrase,
                    headers,
                )
    
            network_stream = self._network_stream
    
            # CONNECT or Upgrade request
            if (status == 101) or (
                (request.method == b"CONNECT") and (200 <= status < 300)
            ):
                network_stream = AsyncHTTP11UpgradeStream(network_stream, trailing_data)
    
            return Response(
                status=status,
                headers=headers,
                content=HTTP11ConnectionByteStream(self, request),
                extensions={
                    "http_version": http_version,
                    "reason_phrase": reason_phrase,
                    "network_stream": network_stream,
                },
            )
        except BaseException as exc:
            with AsyncShieldCancellation():
                async with Trace("response_closed", logger, request) as trace:
                    await self._response_closed()
>           raise exc

.venv/lib/python3.11/site-packages/httpcore/_async/http11.py:136: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <AsyncHTTP11Connection ['http://127.0.0.1:7897', CLOSED, Request Count: 1]>
request = <Request [b'POST']>

    async def handle_async_request(self, request: Request) -> Response:
        if not self.can_handle_request(request.url.origin):
            raise RuntimeError(
                f"Attempted to send request to {request.url.origin} on connection "
                f"to {self._origin}"
            )
    
        async with self._state_lock:
            if self._state in (HTTPConnectionState.NEW, HTTPConnectionState.IDLE):
                self._request_count += 1
                self._state = HTTPConnectionState.ACTIVE
                self._expire_at = None
            else:
                raise ConnectionNotAvailable()
    
        try:
            kwargs = {"request": request}
            try:
                async with Trace(
                    "send_request_headers", logger, request, kwargs
                ) as trace:
                    await self._send_request_headers(**kwargs)
                async with Trace("send_request_body", logger, request, kwargs) as trace:
                    await self._send_request_body(**kwargs)
            except WriteError:
                # If we get a write error while we're writing the request,
                # then we supress this error and move on to attempting to
                # read the response. Servers can sometimes close the request
                # pre-emptively and then respond with a well formed HTTP
                # error response.
                pass
    
            async with Trace(
                "receive_response_headers", logger, request, kwargs
            ) as trace:
                (
                    http_version,
                    status,
                    reason_phrase,
                    headers,
                    trailing_data,
>               ) = await self._receive_response_headers(**kwargs)

.venv/lib/python3.11/site-packages/httpcore/_async/http11.py:106: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <AsyncHTTP11Connection ['http://127.0.0.1:7897', CLOSED, Request Count: 1]>
request = <Request [b'POST']>

    async def _receive_response_headers(
        self, request: Request
    ) -> tuple[bytes, int, bytes, list[tuple[bytes, bytes]], bytes]:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("read", None)
    
        while True:
>           event = await self._receive_event(timeout=timeout)

.venv/lib/python3.11/site-packages/httpcore/_async/http11.py:177: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <AsyncHTTP11Connection ['http://127.0.0.1:7897', CLOSED, Request Count: 1]>
timeout = 30.0

    async def _receive_event(
        self, timeout: float | None = None
    ) -> h11.Event | type[h11.PAUSED]:
        while True:
            with map_exceptions({h11.RemoteProtocolError: RemoteProtocolError}):
                event = self._h11_state.next_event()
    
            if event is h11.NEED_DATA:
>               data = await self._network_stream.read(
                    self.READ_NUM_BYTES, timeout=timeout
                )

.venv/lib/python3.11/site-packages/httpcore/_async/http11.py:217: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <httpcore._backends.anyio.AnyIOStream object at 0x11ad3ef10>
max_bytes = 65536, timeout = 30.0

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        exc_map = {
            TimeoutError: ReadTimeout,
            anyio.BrokenResourceError: ReadError,
            anyio.ClosedResourceError: ReadError,
            anyio.EndOfStream: ReadError,
        }
>       with map_exceptions(exc_map):

.venv/lib/python3.11/site-packages/httpcore/_backends/anyio.py:32: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <contextlib._GeneratorContextManager object at 0x11ad3d610>
typ = <class 'TimeoutError'>, value = TimeoutError()
traceback = <traceback object at 0x11ad3fc80>

    def __exit__(self, typ, value, traceback):
        if typ is None:
            try:
                next(self.gen)
            except StopIteration:
                return False
            else:
                try:
                    raise RuntimeError("generator didn't stop")
                finally:
                    self.gen.close()
        else:
            if value is None:
                # Need to force instantiation so we can reliably
                # tell if we get the same exception back
                value = typ()
            try:
>               self.gen.throw(typ, value, traceback)

../../../../.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/contextlib.py:158: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

map = {<class 'TimeoutError'>: <class 'httpcore.ReadTimeout'>, <class 'anyio.BrokenResourceError'>: <class 'httpcore.ReadErr... 'anyio.ClosedResourceError'>: <class 'httpcore.ReadError'>, <class 'anyio.EndOfStream'>: <class 'httpcore.ReadError'>}

    @contextlib.contextmanager
    def map_exceptions(map: ExceptionMapping) -> typing.Iterator[None]:
        try:
            yield
        except Exception as exc:  # noqa: PIE786
            for from_exc, to_exc in map.items():
                if isinstance(exc, from_exc):
>                   raise to_exc(exc) from exc
E                   httpcore.ReadTimeout

.venv/lib/python3.11/site-packages/httpcore/_exceptions.py:14: ReadTimeout

The above exception was the direct cause of the following exception:

self = <tests.e2e.test_27_macro_self_heal.TestWebMacroSelfHeal object at 0x118176b10>
http_client = <httpx.AsyncClient object at 0x1184d7950>
thread_id = 'e2e-6e62eac6d3d04693'

    @pytest.mark.timeout(120)
    async def test_failing_web_macro_falls_back(self, http_client: httpx.AsyncClient, thread_id: str) -> None:
        """web 源触发必然失败的宏 → 自愈回退（fell_back=True）。"""
        macro_id = await _create_failing_macro(http_client, "ack", "麻烦对对对")
        try:
            await _wait_for_macro_in_spec(http_client, macro_id)
>           resp = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": "麻烦对对对", "project_id": 0},
            )

tests/e2e/test_27_macro_self_heal.py:24: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <httpx.AsyncClient object at 0x1184d7950>, url = '/api/v1/chat'

    async def post(
        self,
        url: URL | str,
        *,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        json: typing.Any | None = None,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: AuthTypes | UseClientDefault = USE_CLIENT_DEFAULT,
        follow_redirects: bool | UseClientDefault = USE_CLIENT_DEFAULT,
        timeout: TimeoutTypes | UseClientDefault = USE_CLIENT_DEFAULT,
        extensions: RequestExtensions | None = None,
    ) -> Response:
        """
        Send a `POST` request.
    
        **Parameters**: See `httpx.request`.
        """
>       return await self.request(
            "POST",
            url,
            content=content,
            data=data,
            files=files,
            json=json,
            params=params,
            headers=headers,
            cookies=cookies,
            auth=auth,
            follow_redirects=follow_redirects,
            timeout=timeout,
            extensions=extensions,
        )

.venv/lib/python3.11/site-packages/httpx/_client.py:1859: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <httpx.AsyncClient object at 0x1184d7950>, method = 'POST'
url = '/api/v1/chat'

    async def request(
        self,
        method: str,
        url: URL | str,
        *,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        json: typing.Any | None = None,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: AuthTypes | UseClientDefault | None = USE_CLIENT_DEFAULT,
        follow_redirects: bool | UseClientDefault = USE_CLIENT_DEFAULT,
        timeout: TimeoutTypes | UseClientDefault = USE_CLIENT_DEFAULT,
        extensions: RequestExtensions | None = None,
    ) -> Response:
        """
        Build and send a request.
    
        Equivalent to:
    
        ```python
        request = client.build_request(...)
        response = await client.send(request, ...)
        ```
    
        See `AsyncClient.build_request()`, `AsyncClient.send()`
        and [Merging of configuration][0] for how the various parameters
        are merged with client-level configuration.
    
        [0]: /advanced/clients/#merging-of-configuration
        """
    
        if cookies is not None:  # pragma: no cover
            message = (
                "Setting per-request cookies=<...> is being deprecated, because "
                "the expected behaviour on cookie persistence is ambiguous. Set "
                "cookies directly on the client instance instead."
            )
            warnings.warn(message, DeprecationWarning, stacklevel=2)
    
        request = self.build_request(
            method=method,
            url=url,
            content=content,
            data=data,
            files=files,
            json=json,
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=timeout,
            extensions=extensions,
        )
>       return await self.send(request, auth=auth, follow_redirects=follow_redirects)

.venv/lib/python3.11/site-packages/httpx/_client.py:1540: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <httpx.AsyncClient object at 0x1184d7950>
request = <Request('POST', 'http://127.0.0.1:20160/api/v1/chat')>

    async def send(
        self,
        request: Request,
        *,
        stream: bool = False,
        auth: AuthTypes | UseClientDefault | None = USE_CLIENT_DEFAULT,
        follow_redirects: bool | UseClientDefault = USE_CLIENT_DEFAULT,
    ) -> Response:
        """
        Send a request.
    
        The request is sent as-is, unmodified.
    
        Typically you'll want to build one with `AsyncClient.build_request()`
        so that any client-level configuration is merged into the request,
        but passing an explicit `httpx.Request()` is supported as well.
    
        See also: [Request instances][0]
    
        [0]: /advanced/clients/#request-instances
        """
        if self._state == ClientState.CLOSED:
            raise RuntimeError("Cannot send a request, as the client has been closed.")
    
        self._state = ClientState.OPENED
        follow_redirects = (
            self.follow_redirects
            if isinstance(follow_redirects, UseClientDefault)
            else follow_redirects
        )
    
        self._set_timeout(request)
    
        auth = self._build_request_auth(request, auth)
    
>       response = await self._send_handling_auth(
            request,
            auth=auth,
            follow_redirects=follow_redirects,
            history=[],
        )

.venv/lib/python3.11/site-packages/httpx/_client.py:1629: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <httpx.AsyncClient object at 0x1184d7950>
request = <Request('POST', 'http://127.0.0.1:20160/api/v1/chat')>
auth = <httpx.Auth object at 0x1040bebd0>, follow_redirects = False
history = []

    async def _send_handling_auth(
        self,
        request: Request,
        auth: Auth,
        follow_redirects: bool,
        history: list[Response],
    ) -> Response:
        auth_flow = auth.async_auth_flow(request)
        try:
            request = await auth_flow.__anext__()
    
            while True:
>               response = await self._send_handling_redirects(
                    request,
                    follow_redirects=follow_redirects,
                    history=history,
                )

.venv/lib/python3.11/site-packages/httpx/_client.py:1657: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <httpx.AsyncClient object at 0x1184d7950>
request = <Request('POST', 'http://127.0.0.1:20160/api/v1/chat')>
follow_redirects = False, history = []

    async def _send_handling_redirects(
        self,
        request: Request,
        follow_redirects: bool,
        history: list[Response],
    ) -> Response:
        while True:
            if len(history) > self.max_redirects:
                raise TooManyRedirects(
                    "Exceeded maximum allowed redirects.", request=request
                )
    
            for hook in self._event_hooks["request"]:
                await hook(request)
    
>           response = await self._send_single_request(request)

.venv/lib/python3.11/site-packages/httpx/_client.py:1694: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <httpx.AsyncClient object at 0x1184d7950>
request = <Request('POST', 'http://127.0.0.1:20160/api/v1/chat')>

    async def _send_single_request(self, request: Request) -> Response:
        """
        Sends a single request, without handling any redirections.
        """
        transport = self._transport_for_url(request.url)
        start = time.perf_counter()
    
        if not isinstance(request.stream, AsyncByteStream):
            raise RuntimeError(
                "Attempted to send an sync request with an AsyncClient instance."
            )
    
        with request_context(request=request):
>           response = await transport.handle_async_request(request)

.venv/lib/python3.11/site-packages/httpx/_client.py:1730: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <httpx.AsyncHTTPTransport object at 0x1184f4c50>
request = <Request('POST', 'http://127.0.0.1:20160/api/v1/chat')>

    async def handle_async_request(
        self,
        request: Request,
    ) -> Response:
        assert isinstance(request.stream, AsyncByteStream)
        import httpcore
    
        req = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
>       with map_httpcore_exceptions():

.venv/lib/python3.11/site-packages/httpx/_transports/default.py:393: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <contextlib._GeneratorContextManager object at 0x11ad3d790>
typ = <class 'httpcore.ReadTimeout'>, value = ReadTimeout(TimeoutError())
traceback = <traceback object at 0x11ad3f300>

    def __exit__(self, typ, value, traceback):
        if typ is None:
            try:
                next(self.gen)
            except StopIteration:
                return False
            else:
                try:
                    raise RuntimeError("generator didn't stop")
                finally:
                    self.gen.close()
        else:
            if value is None:
                # Need to force instantiation so we can reliably
                # tell if we get the same exception back
                value = typ()
            try:
>               self.gen.throw(typ, value, traceback)

../../../../.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/contextlib.py:158: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

    @contextlib.contextmanager
    def map_httpcore_exceptions() -> typing.Iterator[None]:
        global HTTPCORE_EXC_MAP
        if len(HTTPCORE_EXC_MAP) == 0:
            HTTPCORE_EXC_MAP = _load_httpcore_exceptions()
        try:
            yield
        except Exception as exc:
            mapped_exc = None
    
            for from_exc, to_exc in HTTPCORE_EXC_MAP.items():
                if not isinstance(exc, from_exc):
                    continue
                # We want to map to the most specific exception we can find.
                # Eg if `exc` is an `httpcore.ReadTimeout`, we want to map to
                # `httpx.ReadTimeout`, not just `httpx.TimeoutException`.
                if mapped_exc is None or issubclass(to_exc, mapped_exc):
                    mapped_exc = to_exc
    
            if mapped_exc is None:  # pragma: no cover
                raise
    
            message = str(exc)
>           raise mapped_exc(message) from exc
E           httpx.ReadTimeout

.venv/lib/python3.11/site-packages/httpx/_transports/default.py:118: ReadTimeout
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_27_macro_self_heal.py::TestWebMacroSelfHeal::test_failing_web_macro_falls_back -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
