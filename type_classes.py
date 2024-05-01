from typing import Literal, Never, Required, TypedDict

type Category = Literal[
    'creature',
    'planeswalker',
    'instant',
    'sorcery',
    'land',
    'enchantment',
    'artifact',
    'token',
]


class GetGalleryGlobalOptions(TypedDict, total=False):
    category: Literal[Category, 'all']
    language: (
        Literal[
            'en', 'es', 'fr', 'de', 'it', 'pt', 'ja', 'ko', 'ru', 'zhs', 'zht', 'ph'
        ]
        | None
    )
    nsfw: bool | None
    order: Required[Literal['recent', 'top']]
    real: Required[bool]


class GetGalleryOptions(GetGalleryGlobalOptions, total=False):
    user_id: str | None


class CardInfo(TypedDict):
    artist_name: Literal['']
    card_edition: str
    card_id: str | None  # 'hex-hex-hex-hex-hex' | None
    category: Literal[Category, 'card', 'other']
    dislikes: None
    email: str
    face: Literal['single']
    id: str  # str(int)
    image_url: str
    likes: str | None  # str(int) | None
    nsfw: Literal['0', '1']
    pp_id: None
    prints_regular: Literal['0']
    search_card_name: str
    status: Literal['1']
    tags: str | None  # 'tag1, tag2, ...' | None
    user_id: str  # str(int)
    user_name: str
    visual_type: Literal['custom', 'real']


GalleryPage = TypedDict(
    'GalleryPage',
    {
        'current': int,
        'data': list[CardInfo],
        'is': Literal['0'],
        'liked': list[Never],
        'total': int,
    },
)


class TextSettings(TypedDict):
    name: str | None
    text: str


class Frame(TypedDict):
    category: str | None
    name: str
    src: str | None


type Text = dict[str, TextSettings]


class PlaneswalkerOrSaga(TypedDict):
    abilities: list[str]
    count: int


class Info(TypedDict):
    artist: str
    language: str
    number: str
    rarity: str
    set: str
    year: str


class CardData(TypedDict):
    frames: list[Frame]
    info: Info
    planeswalker: PlaneswalkerOrSaga | None
    saga: PlaneswalkerOrSaga | None
    set_symbol: str | None
    text: Text
    version: str


class Card(TypedDict):
    info: CardInfo
    data: CardData
