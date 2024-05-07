from __future__ import annotations

import json
from asyncio import Task, TaskGroup, run, sleep
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import asynccontextmanager
from random import choice, randint
from typing import Any, Unpack

from aiohttp import ClientConnectionError, ClientSession
from async_lru import alru_cache
from tqdm import tqdm

from type_classes import (
    Card,
    CardData,
    CardInfo,
    GalleryPage,
    GetGalleryGlobalOptions,
    GetGalleryOptions,
)


class Session:
    session: ClientSession

    def __init__(self) -> None:
        self.session = ClientSession()

        self.send_request = alru_cache(self._send_request)

    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *_) -> None:
        await self.session.close()

    async def _send_request(
        self, method: str, params: tuple[tuple[str, Any], ...]
    ) -> Any:
        for i in range(10):
            try:
                async with self.session.post(
                    'https://mtgcardbuilder.com/wp-admin/admin-ajax.php',
                    data={'action': 'builder_ajax', 'method': method, **dict(params)},
                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                ) as response:
                    return json.loads(await response.text())
            except ClientConnectionError as err:
                tqdm.write(f'[attempt {i}] {type(err).__name__}: {err}')
                await sleep(1)
        raise ClientConnectionError

    async def fetch_card_data(self, card_id: str) -> CardData:
        data = json.loads(
            (await self.send_request('getCardData', (('id', card_id),)))['data']
        )

        return {
            'frames': [
                {
                    'category': frame.get('cat'),
                    'name': frame['name'],
                    'src': frame['src'] if len(frame['src']) <= 1000 else None,
                }
                for frame in data['frames']
            ],
            'info': {
                'artist': data['infoArtist'],
                'language': data['infoLanguage'],
                'number': data['infoNumber'],
                'rarity': data['infoRarity'],
                'set': data['infoSet'],
                'year': data['infoYear'],
            },
            'planeswalker': (
                {
                    'abilities': data['planeswalker']['abilities'],
                    'count': data['planeswalker']['count'],
                }
                if 'planeswalker' in data
                else None
            ),
            'saga': (
                {'abilities': data['saga']['abilities'], 'count': data['saga']['count']}
                if 'saga' in data
                else None
            ),
            'set_symbol': (
                data['setSymbolSource']
                if data['setSymbolSource'].startswith('https://www.mtgcardbuilder.com/')
                else None
            ),
            'text': {  # type: ignore
                text: {'name': settings.get('name'), 'text': settings['text']}
                for text, settings in data['text'].items()
            },
            'version': data['version'],
        }


class TooManyPages(Exception):
    pass


class CardGallery:
    session: Session
    options: GetGalleryOptions

    def __init__(self, session: Session, **kwargs: Unpack[GetGalleryOptions]) -> None:
        self.session = session
        self.options = kwargs

    async def total_pages(self) -> int:
        return (await self.fetch_page(1))['total']

    async def fetch_page(self, page: int) -> GalleryPage:
        result = await self.session.send_request(
            'get_gallery_cards',
            tuple(
                (key, value)
                for key, value in {
                    'category': (
                        self.options['category']
                        if 'category' in self.options
                        else 'all'
                    ),
                    'cpage': page,
                    'lang': (
                        self.options['language'] if 'language' in self.options else None
                    ),
                    'nsfw': (
                        int(self.options['nsfw'])
                        if 'nsfw' in self.options and self.options['nsfw'] is not None
                        else None
                    ),
                    'order': self.options['order'],
                    'other': int(not self.options['real']),
                    'showIsDashboard': (
                        self.options['user_id'] if 'user_id' in self.options else None
                    ),
                }.items()
                if value is not None
            ),
        )
        for info in result['data']:
            info['category'] = info['category'].lower()
        return result

    async def fetch_all_cards_in_page(self, page: int) -> dict[str, Card]:
        cards_info = (await self.fetch_page(page))['data']

        card_tasks: list[Task[CardData]] = []

        async with TaskGroup() as task_group:
            for card_info in cards_info:
                card_tasks.append(
                    task_group.create_task(
                        self.session.fetch_card_data(card_info['id'])
                    )
                )

        return {
            info['id']: {'info': info, 'data': task.result()}
            for info, task in zip(cards_info, card_tasks)
        }

    async def fetch_all_cards(self) -> dict[str, Card]:
        pages = await self.total_pages()
        if pages > 20:
            raise TooManyPages

        with tqdm(total=pages, desc='Pages', leave=None) as progressbar:
            async with TaskGroup() as task_group:
                tasks: list[Task[dict[str, Card]]] = []
                for page in range(1, pages + 1):
                    task = task_group.create_task(self.fetch_all_cards_in_page(page))
                    task.add_done_callback(lambda _: progressbar.update())
                    tasks.append(task)

        return {
            card_id: card for task in tasks for card_id, card in task.result().items()
        }

    async def fetch_random_card_info(self) -> CardInfo:
        page = randint(1, await self.total_pages())
        cards = (await self.fetch_page(page))['data']
        return choice(cards)


class CardFetcher:
    session: Session
    options: GetGalleryGlobalOptions
    users: dict[str, dict[str, Card]]
    gallery: CardGallery

    def __init__(
        self, session: Session, **kwargs: Unpack[GetGalleryGlobalOptions]
    ) -> None:
        self.session = session
        self.options = kwargs
        self.users = {}
        self.gallery = CardGallery(self.session, **self.options)

    @asynccontextmanager
    async def get_user_gallery(self, user_id: str) -> AsyncGenerator[CardGallery, None]:
        session = Session()
        gallery = CardGallery(session, **self.options, user_id=user_id)
        async with session:
            yield gallery

    def add_user(self, user_id: str) -> None:
        if user_id not in self.users:
            self.users[user_id] = {}

    async def add_random_user(self) -> str:
        info = await self.gallery.fetch_random_card_info()
        self.add_user(info['user_id'])
        return info['user_id']

    async def add_random_user_gallery(self) -> None:
        for _ in range(3):
            user_id = await self.add_random_user()
            try:
                async with self.get_user_gallery(user_id) as user_gallery:
                    self.users[user_id] |= {
                        card_id: card
                        for card_id, card in (
                            await user_gallery.fetch_all_cards()
                        ).items()
                        if 'language' not in self.options
                        or self.options['language'] is None
                        or card['data']['info']['language'].lower()
                        in ['', self.options['language']]
                    }
            except TooManyPages:
                pass
            else:
                return
        raise TooManyPages

    async def add_random_card(self):
        card = await self.gallery.fetch_random_card_info()

        self.add_user(card['user_id'])

        self.users[card['user_id']][card['id']] = {
            'info': card,
            'data': await self.session.fetch_card_data(card['id']),
        }


async def repeat_async(
    func: Callable[[], Coroutine[Any, Any, Any]],
    amount: int,
    description: str | None = None,
):
    with tqdm(total=amount, desc=description) as progress_bar:
        async with TaskGroup() as task_group:
            for _ in range(amount):
                task_group.create_task(func()).add_done_callback(
                    lambda _: progress_bar.update()
                )


async def main() -> None:
    async with Session() as session:
        fetcher = CardFetcher(
            session, order='recent', real=False, language='en', nsfw=False
        )
        await repeat_async(fetcher.add_random_user_gallery, 10, 'Users')

    with open('cards.json', 'w', encoding='utf-8') as file:
        json.dump(fetcher.users, file, indent=2)


if __name__ == '__main__':
    run(main())
