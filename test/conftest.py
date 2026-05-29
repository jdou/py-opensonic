from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from libopensonic import AsyncConnection
from libopensonic._async.connection import API_VERSION


@pytest.fixture
def mock_session():
    """Create a mocked aiohttp ClientSession."""
    session = AsyncMock(spec=aiohttp.ClientSession)
    return session


@pytest.fixture
def mock_response():
    """Create a mocked ClientResponse for JSON responses."""
    response = AsyncMock(spec=aiohttp.ClientResponse)
    response.raise_for_status = Mock(return_value=None)
    response.headers = {"Content-Type": "application/json"}
    return response


@pytest.fixture
def mock_binary_response():
    """Create a mocked ClientResponse for binary responses."""
    response = AsyncMock(spec=aiohttp.ClientResponse)
    response.raise_for_status = Mock(return_value=None)
    response.headers = {"Content-Type": "application/octet-stream"}
    response.content = b"binary data"
    return response


@pytest.fixture
def conn(mock_session):
    """Create an AsyncConnection with mocked session."""
    with patch('aiohttp.ClientSession', return_value=mock_session):
        c = AsyncConnection(
            base_url="http://localhost",
            username="testuser",
            password="testpass",
            port=4040,
            app_name="test-app",
            legacy_auth=False,
            use_get=False,
            use_views=True
        )
        c._sess = mock_session
        return c


@pytest.fixture
def base_subsonic_response():
    """Return a minimal successful subsonic response."""
    return {
        "subsonic-response": {
            "status": "ok",
            "version": API_VERSION
        }
    }
