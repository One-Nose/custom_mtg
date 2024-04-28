import json
import re
from collections.abc import Callable
from xml.etree.ElementTree import Element, SubElement, indent, tostring

import requests

from type_classes import Card, TextSettings


class TranslationError(Exception):
    pass


def set_exists(sets: Element, name: str) -> bool:
    for element in sets.iter('set'):
        if getattr(element.find('name'), 'text', None) == name:
            return True
    return False


def add_set(sets: Element, card: Card) -> None:
    set_name = card['data']['info']['set']

    if set_name == 'MTG':
        username = card['info']['user_name']
        set_longname = f'MTGCardBuilder User {username}'
        set_name = 'MCBU-' + username.upper()
    else:
        set_longname = f'MTGCardBuilder Set {set_name}'
        set_name = 'MCB-' + set_name

    if not set_exists(sets, set_name):
        set_element = SubElement(sets, 'set')

        name = SubElement(set_element, 'name')
        name.text = set_name

        longname = SubElement(set_element, 'longname')
        longname.text = set_longname

        settype = SubElement(set_element, 'settype')
        settype.text = 'Custom'

        SubElement(set_element, 'releasedate')


def add_text(card_element: Element, card: Card) -> None:
    text = SubElement(card_element, 'text')

    if (
        'planeswalker' in card['data']['version'].lower()
        and card['data']['planeswalker'] is not None
    ):
        abilities: list[str] = []
        for i in range(card['data']['planeswalker']['count']):
            ability = card['data']['planeswalker']['abilities'][i]
            if ability != '':
                ability = f'[{ability}]: '
            ability_text: TextSettings | None = card['data']['text'].get(f'ability{i}')
            if ability_text is not None:
                ability += ability_text['text']

            abilities.append(ability)

        text.text = '\n'.join(abilities)
    elif 'saga' in card['data']['version'].lower() and card['data']['saga'] is not None:
        abilities: list[str] = []

        if 'reminder' in card['data']['text']:
            abilities.append(card['data']['text']['reminder']['text'])

        lore = 1
        lore_names = {1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI'}
        for i in range(card['data']['saga']['count']):
            lores = int(card['data']['saga']['abilities'][i])

            ability = lore_names.get(lore, str(lore))
            lore += 1

            for i in range(lores - 1):
                ability += ', ' + lore_names.get(lore, str(lore))
                lore += 1

            ability += ' — '

            ability_text: TextSettings | None = card['data']['text'].get(f'ability{i}')
            if ability_text is not None:
                ability += ability_text['text']

            abilities.append(ability)

        text.text = '\n'.join(abilities)
    elif 'class' in card['data']['version']:
        rules_text = (
            card['data']['text']['level0c']['text'] + '\n'
            if 'level0c' in card['data']['text']
            else ''
        )

        for level in ('1', '2', '3'):
            level_text = f'level{level}a'
            if card['data']['text'].get(level_text, '') != '':
                rules_text += card['data']['text'][level_text]['text'] + ' '

            level_text = f'level{level}b'
            if card['data']['text'].get(level_text, '') != '':
                rules_text += card['data']['text'][level_text]['text'] + '\n'

            level_text = f'level{level}c'
            if card['data']['text'].get(level_text, '') != '':
                rules_text += card['data']['text'][level_text]['text']

            rules_text += '\n'

        text.text = rules_text

    else:
        text.text = card['data']['text'].get('rules', {'text': ''})['text']

    replace_options: dict[str, str | Callable[[re.Match[str]], str]] = {
        r'\n\{i}.+\{/i}(\n|$)': '',
        r'\{cardname}': get_card_name(card),
        r'\{-}': '—',
        (
            r'\{/?'
            r'(i|bold'
            r'|fontsize-?\d+(pt)?'
            r'|fontcolor.+?'
            r'|(justify)?(left|center|right)'
            r'|permashift-?\d+,-?\d+'
            r'|(up|down|left|right|shadow)-?\d+'
            r'|shadowcolor.+?'
            r'|indent'
            r'|kerning-?\d+'
            r'|bar'
            r')}'
        ): '',
        r'\{lns}': ' ',
        r'\{roll(.+?)}': r'\1',
        r'\{.+?}': lambda match: match[0].upper(),
        r'\{(w/?u|u/?w)}': '{W/U}',
        r'\{(w/?b|b/?w)}': '{W/B}',
        r'\{(u/?b|b/?u)}': '{U/B}',
        r'\{(u/?r|r/?u)}': '{U/R}',
        r'\{(b/?r|r/?b)}': '{B/R}',
        r'\{(b/?g|g/?b)}': '{B/G}',
        r'\{(r/?g|g/?r)}': '{R/G}',
        r'\{(r/?w|w/?r)}': '{R/W}',
        r'\{(g/?w|w/?g)}': '{G/W}',
        r'\{(g/?u|u/?g)}': '{G/U}',
        r'\{(2/?w|w/?2)}': '{2/W}',
        r'\{(2/?u|u/?2)}': '{2/U}',
        r'\{(2/?b|b/?2)}': '{2/B}',
        r'\{(2/?r|r/?2)}': '{2/R}',
        r'\{(2/?g|g/?2)}': '{2/G}',
        r'\{(p/?w|w/?p)}': '{W/P}',
        r'\{(p/?u|u/?p)}': '{U/P}',
        r'\{(p/?b|b/?p)}': '{B/P}',
        r'\{(p/?r|r/?p)}': '{R/P}',
        r'\{(p/?g|g/?p)}': '{G/P}',
        r'\{([wubrg])/?([wubrg])/?p}': (
            lambda match: '{' + f'{match[1].upper()}/{match[2].upper()}/P' + '}'
        ),
        r'\{untap}': '{Q}',
        r'\{(t|oldtap|originaltap)}': '{T}',
        r'\{\+0}': '[0]',
        r'\{([+-][1-9])}': '[\1]',
    }

    for pattern, replace in replace_options.items():
        regex = re.compile(pattern, re.IGNORECASE)
        text.text = re.sub(regex, replace, text.text)  # type: ignore

    text.text = re.split(r'\{(divider|flavor)\}', text.text, 1, re.IGNORECASE)[0]


def add_card(cards: Element, card: Card) -> None:
    card_element = SubElement(cards, 'card')

    name = SubElement(card_element, 'name')
    name.text = get_card_name(card)

    add_text(card_element, card)

    if (
        card['info']['category'] == 'token'
        or 'token'
        in card['data']['text'].get('type', {'text': ''})['text'].lower().split()
    ):
        SubElement(card_element, 'token').text = '1'

    SubElement(card_element, 'set', picurl=card['info']['image_url'])


def get_card_name(card: Card) -> str:
    if 'title' in card['data']['text'] and card['data']['text']['title']['text'] != '':
        return re.sub(r'\{.+?\}', '', card['data']['text']['title']['text']).strip()
    search_card_name = card['info']['search_card_name']
    return (
        card['info']['card_edition'] if search_card_name == 'null' else search_card_name
    )


def main():
    card_names: list[str] = requests.get(
        'https://api.scryfall.com/catalog/card-names', timeout=10
    ).json()['data']

    for name in card_names:
        if ' // ' in name:
            card_names += name.split(' // ')

    with open('cards.json', encoding='utf-8') as file:
        data: dict[str, dict[str, Card]] = json.load(file)

    root = Element('cockatrice_carddatabase', version='4')

    sets = SubElement(root, 'sets')
    cards = SubElement(root, 'cards')

    for user, user_cards in data.items():
        has_original_cards = False
        for card in user_cards.values():
            if (
                card['info']['visual_type'] == 'custom'
                and card['info']['category'] not in ['token', 'other']
                and 'type' in card['data']['text']
                and 'token' not in card['data']['text']['type']['text'].lower().split()
                and (
                    card['info']['category'] == 'planeswalker'
                    or (
                        'rules' in card['data']['text']
                        and card['data']['text']['rules']['text'] != ''
                    )
                )
                and ' '.join(
                    filter(
                        lambda word: not word.isnumeric(), get_card_name(card).split()
                    )
                )
                not in card_names
            ):
                print(get_card_name(card))
                has_original_cards = True
                break

        if not has_original_cards:
            print(f'skipping user {user}')
            continue

        for card in user_cards.values():
            add_set(sets, card)
            add_card(cards, card)

    indent(root)

    with open('01.customcards.xml', 'w', encoding='utf-8') as file:
        file.write(
            tostring(
                root,
                encoding='unicode',
                xml_declaration=True,
                short_empty_elements=False,
            )
        )


if __name__ == '__main__':
    main()
