"""
This file is part of py-opensonic.

py-opensonic is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

py-opensonic is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with py-opensonic.  If not, see <http://www.gnu.org/licenses/>
"""

import asyncio
import inspect
import threading
from functools import wraps

from .._async.connection import AsyncConnection, API_VERSION


def _make_sync(async_cls):
    """Class decorator that generates sync wrappers for all public methods of async_cls."""
    def decorator(cls):
        for name in dir(async_cls):
            if name.startswith('_') or name in vars(cls):
                continue

            # Resolve the attribute from the MRO so properties are seen as descriptors.
            raw = None
            for klass in async_cls.__mro__:
                if name in klass.__dict__:
                    raw = klass.__dict__[name]
                    break

            if raw is None:
                continue

            if isinstance(raw, property):
                fget = lambda self, n=name: getattr(self._async, n)
                fset = (lambda self, v, n=name: setattr(self._async, n, v)) if raw.fset else None
                setattr(cls, name, property(fget, fset, doc=raw.__doc__))

            elif inspect.iscoroutinefunction(raw):
                def make_wrapper(m):
                    @wraps(m)
                    def wrapper(self, *args, **kwargs):
                        return asyncio.run_coroutine_threadsafe(
                            m(self._async, *args, **kwargs), self._loop
                        ).result()
                    return wrapper
                setattr(cls, name, make_wrapper(raw))

            elif callable(raw):
                def make_delegator(m):
                    @wraps(m)
                    def delegator(self, *args, **kwargs):
                        return m(self._async, *args, **kwargs)
                    return delegator
                setattr(cls, name, make_delegator(raw))

        return cls
    return decorator


@_make_sync(AsyncConnection)
class Connection:
    """Synchronous OpenSubsonic connection backed by AsyncConnection on a private event loop."""

    def __init__(self, base_url: str, username: str | None = None,
                 password: str | None = None, port: int = 4040,
                 api_key: str | None = None, server_path: str = '',
                 app_name: str = 'py-opensonic', api_version: str = API_VERSION,
                 use_netrc: str | None = None, legacy_auth: bool = False,
                 use_get: bool = False, use_views: bool = True):
        """Create a synchronous connection to an OpenSubsonic server.

        Args:
            base_url: The base URL for your server.
            username: Username for authentication.
            password: Password for authentication.
            port: Port number. Default is 4040.
            api_key: API key for authentication (OpenSubsonic extension).
            server_path: Base resource path for the subsonic views.
            app_name: Name of your application.
            api_version: API version to use.
            use_netrc: Path to a netrc file, or True to use ~/.netrc.
            legacy_auth: Use pre-1.13.0 authentication.
            use_get: Use GET requests instead of POST.
            use_views: Append .view to endpoint names.
        """
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._async = AsyncConnection(
            base_url, username=username, password=password, port=port,
            api_key=api_key, server_path=server_path, app_name=app_name,
            api_version=api_version, use_netrc=use_netrc, legacy_auth=legacy_auth,
            use_get=use_get, use_views=use_views,
        )

    def cleanup(self) -> None:
        """Close the connection and stop the background event loop."""
        future = asyncio.run_coroutine_threadsafe(self._async.cleanup(), self._loop)
        future.result(timeout=10)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
