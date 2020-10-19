import aiohttp
import aiohttp.client_exceptions
import functools
import pathlib
import urllib.parse

from typing import List

from dsw_tdk.consts import DEFAULT_ENCODING, APP, VERSION
from dsw_tdk.model import Template, TemplateFile, TemplateFileType


class DSWCommunicationError(RuntimeError):

    def __init__(self, reason: str, message: str):
        self.reason = reason
        self.message = message


def handle_client_errors(func):
    @functools.wraps(func)
    async def handled_client_call(job, *args, **kwargs):
        try:
            return await func(job, *args, **kwargs)
        except DSWCommunicationError as e:
            # Already DSWCommunicationError (re-raise)
            raise e
        except aiohttp.client_exceptions.ContentTypeError as e:
            raise DSWCommunicationError(
                reason='Unexpected response type',
                message=e.message
            )
        except aiohttp.client_exceptions.ClientResponseError as e:
            raise DSWCommunicationError(
                reason='Error response status',
                message=f'Server responded with error HTTP status {e.status}: {e.message}'
            )
        except aiohttp.client_exceptions.InvalidURL as e:
            raise DSWCommunicationError(
                reason='Invalid URL',
                message=f'Provided API URL seems invalid: {e.url}'
            )
        except aiohttp.client_exceptions.ClientConnectorError as e:
            raise DSWCommunicationError(
                reason='Server unreachable',
                message=f'Desired server is not reachable (errno {e.os_error.errno})'
            )
        except Exception as e:
            raise DSWCommunicationError(
                reason='Communication error',
                message=f'Communication with server failed ({e})'
            )
    return handled_client_call


class DSWAPIClient:

    def _headers(self, extra=None):
        headers = {
            'Authorization': f'Bearer {self.token}',
            'User-Agent': f'{APP}/{VERSION}'
        }
        if extra is not None:
            headers.update(extra)
        return headers

    def _check_status(self, r: aiohttp.ClientResponse, expected_status):
        r.raise_for_status()
        if r.status != expected_status:
            raise DSWCommunicationError(
                reason='Unexpected response status',
                message=f'Server responded with unexpected HTTP status {r.status}: '
                        f'{r.reason} (expecting {expected_status})'
            )

    def __init__(self, api_url: str, session=None):
        self.api_url = api_url
        self.token = None
        self.session = session or aiohttp.ClientSession()

    async def close(self):
        await self.session.close()

    async def _post_json(self, endpoint, json) -> dict:
        async with self.session.post(f'{self.api_url}{endpoint}', json=json, headers=self._headers()) as r:
            self._check_status(r, expected_status=201)
            return await r.json()

    async def _put_json(self, endpoint, json) -> dict:
        async with self.session.put(f'{self.api_url}{endpoint}', json=json, headers=self._headers()) as r:
            self._check_status(r, expected_status=200)
            return await r.json()

    async def _get_json(self, endpoint) -> dict:
        async with self.session.get(f'{self.api_url}{endpoint}', headers=self._headers()) as r:
            self._check_status(r, expected_status=200)
            return await r.json()

    async def _get_bytes(self, endpoint) -> bytes:
        async with self.session.get(f'{self.api_url}{endpoint}', headers=self._headers()) as r:
            self._check_status(r, expected_status=200)
            return await r.read()

    async def _delete(self, endpoint) -> bool:
        async with self.session.delete(f'{self.api_url}{endpoint}', headers=self._headers()) as r:
            return r.status == 204

    @handle_client_errors
    async def login(self, email: str, password: str) -> str:
        req = {'email': email, 'password': password}
        body = await self._post_json('/tokens', json=req)
        self.token = body.get('token', None)
        return self.token

    @handle_client_errors
    async def check_template_exists(self, template_id: str) -> bool:
        async with self.session.get(f'{self.api_url}/templates/{template_id}', headers=self._headers()) as r:
            if r.status == 404:
                return False
            self._check_status(r, expected_status=200)
            return True

    @handle_client_errors
    async def get_templates(self) -> List[Template]:
        body = await self._get_json('/templates')
        return list(map(_load_remote_template, body))

    @handle_client_errors
    async def get_template(self, template_id: str) -> Template:
        body = await self._get_json(f'/templates/{template_id}')
        return _load_remote_template(body)

    @handle_client_errors
    async def get_template_files(self, template_id: str) -> List[TemplateFile]:
        body = await self._get_json(f'/templates/{template_id}/files')
        return list(map(_load_remote_file, body))

    @handle_client_errors
    async def get_template_file(self, template_id: str, file_id: str) -> TemplateFile:
        body = await self._get_json(f'/templates/{template_id}/files/{file_id}')
        return _load_remote_file(body)

    @handle_client_errors
    async def get_template_assets(self, template_id: str) -> List[TemplateFile]:
        body = await self._get_json(f'/templates/{template_id}/assets')
        result = []
        for file_body in body:
            asset_id = file_body['uuid']
            content = await self._get_bytes(f'/templates/{template_id}/assets/{asset_id}/content')
            result.append(_load_remote_asset(file_body, content))
        return result

    @handle_client_errors
    async def get_template_asset(self, template_id: str, asset_id: str) -> TemplateFile:
        body = await self._get_json(f'/templates/{template_id}/assets/{asset_id}')
        content = await self._get_bytes(f'/templates/{template_id}/assets/{asset_id}/content')
        return _load_remote_asset(body, content)

    @handle_client_errors
    async def post_template(self, template: Template) -> Template:
        body = await self._post_json(
            endpoint=f'/templates',
            json=template.serialize_remote(),
        )
        return _load_remote_template(body)

    @handle_client_errors
    async def put_template(self, template: Template) -> Template:
        body = await self._put_json(
            endpoint=f'/templates/{template.id}',
            json=template.serialize_remote(),
        )
        return _load_remote_template(body)

    @handle_client_errors
    async def post_template_file(self, template_id: str, tfile: TemplateFile):
        data = await self._post_json(
            endpoint=f'/templates/{template_id}/files',
            json={
                'fileName': tfile.filename.as_posix(),
                'content': tfile.content.decode(DEFAULT_ENCODING)
            }
        )
        return _load_remote_file(data)

    @handle_client_errors
    async def post_template_asset(self, template_id: str, tfile: TemplateFile):
        data = aiohttp.FormData()
        data.add_field('file',
                       tfile.content,
                       filename=tfile.filename.as_posix(),
                       content_type=tfile.content_type)
        async with self.session.post(f'{self.api_url}/templates/{template_id}/assets', data=data, headers=self._headers()) as r:
            self._check_status(r, expected_status=201)
            body = await r.json()
            return _load_remote_asset(body, tfile.content)

    @handle_client_errors
    async def delete_template(self, template_id: str) -> bool:
        return await self._delete(f'/templates/{template_id}')

    @handle_client_errors
    async def delete_template_file(self, template_id: str, file_id: str) -> bool:
        return await self._delete(f'/templates/{template_id}/files/{file_id}')

    @handle_client_errors
    async def delete_template_asset(self, template_id: str, asset_id: str) -> bool:
        return await self._delete(f'/templates/{template_id}/assets/{asset_id}')


def _load_remote_file(data: dict) -> TemplateFile:
    content = data.get('content', None)  # type: str
    template_file = TemplateFile(
        remote_id=data.get('uuid', None),
        remote_type=TemplateFileType.file,
        filename=pathlib.Path(urllib.parse.unquote(data.get('fileName'))),
        content=content.encode(encoding=DEFAULT_ENCODING),
    )
    return template_file


def _load_remote_asset(data: dict, content: bytes) -> TemplateFile:
    template_file = TemplateFile(
        remote_id=data.get('uuid', None),
        remote_type=TemplateFileType.asset,
        filename=pathlib.Path(urllib.parse.unquote(data.get('fileName'))),
        content_type=data.get('contentType', None),
        content=content,
    )
    return template_file


def _load_remote_template(data: dict) -> Template:
    return Template.load_remote(data)