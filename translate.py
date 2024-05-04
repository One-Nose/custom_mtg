import json
import re
from collections.abc import Callable
from difflib import get_close_matches
from xml.etree.ElementTree import Element, SubElement, fromstring, indent, tostring

import requests
from tqdm import tqdm

from type_classes import Card, TextSettings


class TranslationError(Exception):
    pass


def set_exists(sets: Element, name: str) -> bool:
    for element in sets.iter('set'):
        if getattr(element.find('name'), 'text', None) == name:
            return True
    return False


def add_set(sets: Element, card: Card) -> str:
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
        settype.text = 'MTGCardBuilder'

        SubElement(set_element, 'releasedate')

    return set_name


def get_text(card: Card) -> str:
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

        text = '\n'.join(abilities)
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

        text = '\n'.join(abilities)
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

        text = rules_text

    else:
        text = card['data']['text'].get('rules', {'text': ''})['text']

    if card['data']['version'] == 'adventure':
        text += '\n\n---\n\n' + card['data']['text']['rules2']['text']

    return translate_text(text, card)


def translate_text(text: str, card: Card) -> str:
    replace_options: tuple[tuple[str, str | Callable[[re.Match[str]], str]], ...] = (
        (r'\n\{i}.+\{/i}(\n|$)', ''),
        (r'\{cardname}', get_card_name(card, rules_cardname=True)),
        (r'\{-}', '—'),
        (
            r'\{/?'
            r'(i|bold'
            r'|font.+?'
            r'|(justify)?(left|center|right)'
            r'|permashift-?\d+,-?\d+'
            r'|(up|down|left|right)-?\d+'
            r'|shadow.+?'
            r'|indent'
            r'|kerning-?\d+'
            r'|bar'
            r'|planechase'
            r'|color.+?'
            r')}',
            '',
        ),
        (r'\{lns}', ' '),
        (r'\{roll(.+?)}', r'\1'),
        (r'\{.+?}', lambda match: match[0].upper()),
        (r'\{(w/?u|u/?w)}', '{W/U}'),
        (r'\{(w/?b|b/?w)}', '{W/B}'),
        (r'\{(u/?b|b/?u)}', '{U/B}'),
        (r'\{(u/?r|r/?u)}', '{U/R}'),
        (r'\{(b/?r|r/?b)}', '{B/R}'),
        (r'\{(b/?g|g/?b)}', '{B/G}'),
        (r'\{(r/?g|g/?r)}', '{R/G}'),
        (r'\{(r/?w|w/?r)}', '{R/W}'),
        (r'\{(g/?w|w/?g)}', '{G/W}'),
        (r'\{(g/?u|u/?g)}', '{G/U}'),
        (r'\{(2/?w|w/?2)}', '{2/W}'),
        (r'\{(2/?u|u/?2)}', '{2/U}'),
        (r'\{(2/?b|b/?2)}', '{2/B}'),
        (r'\{(2/?r|r/?2)}', '{2/R}'),
        (r'\{(2/?g|g/?2)}', '{2/G}'),
        (r'\{(p/?w|w/?p)}', '{W/P}'),
        (r'\{(p/?u|u/?p)}', '{U/P}'),
        (r'\{(p/?b|b/?p)}', '{B/P}'),
        (r'\{(p/?r|r/?p)}', '{R/P}'),
        (r'\{(p/?g|g/?p)}', '{G/P}'),
        (
            r'\{([wubrg])/?([wubrg])/?p}',
            lambda match: '{' + f'{match[1].upper()}/{match[2].upper()}/P' + '}',
        ),
        (r'\{untap}', '{Q}'),
        (r'\{(t|oldtap|originaltap)}', '{T}'),
        (r'\{\+0}', '[0]'),
        (r'\{([+-][1-9])}', '[\1]'),
    )

    result = text

    for pattern, replace in replace_options:
        regex = re.compile(pattern, re.IGNORECASE)
        result = re.sub(regex, replace, result)

    result: str = re.split(r'\{(divider|flavor)\}', result, 1, re.IGNORECASE)[0]

    return result


def add_card(
    cards: Element,
    card: Card,
    set_name: str,
    user_cards: dict[str, Card],
    back_side: Card | None,
    is_back_side: bool,
    tokens: dict[str, str],
) -> None:
    card_element = SubElement(cards, 'card')

    name = SubElement(card_element, 'name')
    name.text = get_card_name(card)

    text = get_text(card)
    SubElement(card_element, 'text').text = text

    card_types: list[str] = []

    if 'type' in card['data']['text']:
        match = re.match(
            r'([a-zA-Z ]+?)(-|\{-}|$)',
            translate_text(card['data']['text']['type']['text'], card),
        )

        if match:
            card_types = match[1].lower().split()

    prop = SubElement(card_element, 'prop')

    layout = SubElement(prop, 'layout')

    if card['data']['version'] == 'adventure':
        layout.text = 'adventure'
    elif card['data']['version'] == 'planechase':
        layout.text = 'planar'
    elif any(
        string in get_text(card).lower()
        for string in ('transform', 'daybound', 'nightbound')
    ):
        layout.text = 'transform'
    else:
        layout.text = 'normal'

    side = SubElement(prop, 'side')

    if is_back_side:
        side.text = 'back'
    else:
        side.text = 'front'

    type_element = SubElement(prop, 'type')
    type_element.text = translate_text(card['data']['text']['type']['text'], card)

    if layout.text == 'adventure':
        type_element.text = (
            translate_text(card['data']['text']['type2']['text'], card)
            + ' // '
            + type_element.text
        )

    maintype = SubElement(prop, 'maintype')
    card_types = type_element.text.lower().split()

    if 'instant' in card_types:
        maintype.text = 'Instant'
    elif 'sorcery' in card_types:
        maintype.text = 'Sorcery'
    elif 'creature' in card_types:
        maintype.text = 'Creature'
    elif 'planeswalker' in card_types:
        maintype.text = 'Planeswalker'
    elif 'battle' in card_types:
        maintype.text = 'Battle'
    elif 'land' in card_types:
        maintype.text = 'Land'
    elif 'artifact' in card_types:
        maintype.text = 'Artifact'
    elif 'enchantment' in card_types:
        maintype.text = 'Enchantment'
    elif 'hero' in card_types:
        maintype.text = 'Hero'
    elif not card_types and any(
        land_type in get_card_name(card).lower()
        for land_type in ('forest', 'island', 'mountain', 'plains', 'swamp')
    ):
        maintype.text = 'land'
    else:
        try:
            maintype.text = [
                card_type
                for card_type in type_element.text.split()
                if card_type.lower()
                not in (
                    'basic',
                    'host',
                    'legendary',
                    'ongoing',
                    'snow',
                    'token',
                    'world',
                )
            ][0]
        except IndexError:
            prop.remove(maintype)

    cmc = 0
    manacost: Element | None = None
    if 'mana' in card['data']['text']:
        cost, cmc = translate_mana_cost(card['data']['text']['mana']['text'], card)

        if cost:
            manacost = SubElement(prop, 'manacost')
            manacost.text = cost

            if layout.text == 'adventure':
                manacost.text = (
                    translate_mana_cost(card['data']['text']['mana2']['text'], card)[0]
                    + ' // '
                    + manacost.text
                )

    SubElement(prop, 'cmc').text = str(cmc)

    colors = ''
    identity_colors = ''
    for letter, color_name in color_names.items():
        if (manacost is not None and letter in (manacost.text or '').upper()) or (
            any(
                frame['name'] == f'{color_name} Pip' for frame in card['data']['frames']
            )
        ):
            colors += letter
            identity_colors += letter

        elif any(
            text_type.startswith('rules') and '{' + letter + '}' in text['text'].upper()
            for text_type, text in card['data']['text'].items()
        ):
            identity_colors += letter

    if colors:
        SubElement(prop, 'colors').text = colors
    if identity_colors:
        SubElement(prop, 'coloridentity').text = identity_colors

    if card['data']['text'].get('pt', {'text': ''})['text']:
        SubElement(prop, 'pt').text = translate_text(
            card['data']['text']['pt']['text'], card
        ).strip()

    if card['data']['text'].get('loyalty', {'text': ''})['text']:
        SubElement(prop, 'loyalty').text = translate_text(
            card['data']['text']['loyalty']['text'], card
        )

    set_element = SubElement(card_element, 'set', picurl=card['info']['image_url'])
    set_element.text = set_name

    rarities = {'c': 'common', 'u': 'uncommon', 'r': 'rare', 'm': 'mythic'}

    if 'token' not in card_types:
        if card['data']['info']['rarity'] in rarities:
            set_element.attrib['rarity'] = rarities[
                card['data']['info']['rarity'].lower()
            ]
        elif card['data']['set_symbol'] is not None:
            match = re.search(r'-(.)\.svg$', card['data']['set_symbol'])
            if match:
                set_element.attrib['rarity'] = rarities[match[1]]

    match = re.match(r'(\d+)(/\d+)?$', card['data']['info']['number'])
    if match:
        set_element.attrib['num'] = match[1]

    if back_side is not None:
        for string in ('related', 'reverse-related'):
            SubElement(card_element, string, attach='transform').text = get_card_name(
                back_side
            )

    if layout.text == 'adventure':
        SubElement(card_element, 'related', attach='attach').text = 'On an Adventure'

    rules = get_text(card).lower()
    added_tokens: list[str] = []
    for token_string, token_name in tokens.items():
        if token_string in rules and token_name not in added_tokens:
            added_tokens.append(token_name)
            SubElement(card_element, 'related').text = token_name

    for match in re.findall(r'.+ creature token .+', get_text(card).lower()):
        tqdm.write(match)

    if (
        card['info']['category'] == 'token'
        or 'token'
        in card['data']['text'].get('type', {'text': ''})['text'].lower().split()
    ):
        for creating_card in user_cards.values():
            if name.text in get_text(creating_card):
                SubElement(card_element, 'reverse-related').text = get_card_name(
                    creating_card
                )

        SubElement(card_element, 'token').text = '1'

    tablerow = SubElement(card_element, 'tablerow')
    match maintype.text:
        case 'Land':
            tablerow.text = '0'
        case 'Artifact' | 'Enchantment' | 'Planeswalker':
            tablerow.text = '1'
        case 'Creature':
            tablerow.text = '2'
        case 'Instant' | 'Sorcery':
            tablerow.text = '3'
        case _:
            match card['info']['category']:
                case 'land':
                    tablerow.text = '0'
                case 'artifact' | 'enchantment' | 'planeswalker':
                    tablerow.text = '1'
                case 'creature':
                    tablerow.text = '2'
                case 'instant' | 'sorcery':
                    tablerow.text = '3'
                case _:
                    if 'creature' in card_types:
                        tablerow.text = '2'
                    elif 'land' in card_types:
                        tablerow.text = '0'
                    else:
                        tablerow.text = '1'

    if any(
        f'{s.lower()} enters the battlefield tapped' in text.lower()
        for s in (name.text, 'this creature', 'this card')
    ):
        SubElement(card_element, 'cipt').text = '1'

    # SubElement(card_element, 'upsidedown').text = '1'


def translate_mana_cost(mana_cost: str, card: Card) -> tuple[str, int]:
    costs: list[str] = [
        (
            cost
            if len(cost) <= 1 or cost.isnumeric()
            else translate_text('{' + cost + '}', card)
        )
        for cost in re.split(r'[ {}]', mana_cost.upper())
    ]

    cmc = 0

    for cost in costs:
        if cost.isnumeric():
            cmc += int(cost)
        elif '2' in cost:
            cmc += 2
        elif cost:
            cmc += 1

    return ''.join(costs), cmc


def get_card_name(card: Card, rules_cardname: bool = False) -> str:
    if 'title' in card['data']['text'] and card['data']['text']['title']['text'] != '':
        name = card['data']['text']['title']['text']

        if not rules_cardname and card['data']['version'] == 'adventure':
            name += ' // ' + card['data']['text']['title2']['text']

        return re.sub(r'\{.+?\}', '', name).strip()
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

    tokens = {
        'blood token': 'Blood Token',
        'clue token': 'Clue Token',
        'food token': 'Food Token',
        'gold token': 'Gold Token',
        'incubator token': 'Incubator Token',
        'junk token': 'Junk Token',
        'map token': 'Map Token',
        'powerstone token': 'Powerstone Token',
        'treasure token': 'Treasure Token',
        'shard token': 'Shard Token',
        'walker token': 'Walker Token',
        'daybound': 'Day',
    }

    tokens_xml = fromstring(
        requests.get(
            'https://raw.githubusercontent.com/Cockatrice/Magic-Token/master/tokens.xml',
            timeout=10,
        ).text
    )

    for token in tokens_xml.iter('card'):
        name = token.find('name')
        if name is None or name.text is None:
            continue

        if not name.text.rstrip().endswith(' Token'):
            continue

        prop = token.find('prop')
        if prop is None:
            continue

        pt = prop.find('pt')
        if pt is None or pt.text is None:
            continue

        token_string = pt.text + ' '

        colors_element = prop.find('colors')
        colors = '' if colors_element is None else colors_element.text or ''

        if len(colors) > 2:
            continue

        if colors == '':
            token_string += 'colorless '
        else:
            token_string += ' and '.join([color_names[color] for color in colors]) + ' '

        type_element = prop.find('type')
        if type_element is None or type_element.text is None:
            continue

        types = type_element.text.split('—')
        if len(types) != 2 or not re.match(r'token.* creature .*', types[0].lower()):
            continue

        token_string += types[1].strip() + ' '
        token_string += types[0][len('token') :].strip() + ' '
        tokens_string = token_string
        token_string += 'token'
        tokens_string += 'tokens'

        text = token.find('text')
        if text is not None:
            if text.text is None or '\n' in text.text:
                continue

            abilities = text.text.split(', ')

            with_string = ' with'

            for i, ability in enumerate(abilities):
                if i == 0:
                    with_string += ' ' + ability
                elif i == len(abilities) - 1:
                    with_string += ' and ' + ability
                else:
                    with_string += ', ' + ability

            token_string += with_string
            tokens_string += with_string

        tokens[token_string.lower()] = name.text
        tokens[tokens_string.lower()] = name.text

    with open('cards.json', encoding='utf-8') as file:
        data: dict[str, dict[str, Card]] = json.load(file)

    root = Element('cockatrice_carddatabase', version='4')

    root.attrib['xmlns:xsi'] = 'http://www.w3.org/2001/XMLSchema-instance'
    schema = (
        'https://raw.githubusercontent.com/Cockatrice'
        '/Cockatrice/master/doc/carddatabase_v4/cards.xsd'
    )
    root.attrib['xsi:noNamespaceSchemaLocation'] = schema

    sets = SubElement(root, 'sets')
    cards = SubElement(root, 'cards')

    for user, user_cards in tqdm(data.items(), 'Users'):
        has_original_cards = False
        for i, card in enumerate(tqdm(user_cards.values(), 'Cards', leave=None)):
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
                and len(get_close_matches(get_card_name(card), card_names, cutoff=0.9))
                == 0
            ):
                tqdm.write(get_card_name(card))
                has_original_cards = True
                break

            if i > 20:
                break

        if not has_original_cards:
            tqdm.write(f'skipping user {user}')
            continue

        dfcs: dict[str, str] = {}
        for card in user_cards.values():
            card_text = get_text(card).lower()
            options: list[Card] = []

            if 'nightbound' not in card_text:
                if 'daybound' in card_text:
                    for nightbound in user_cards.values():
                        if (
                            'nightbound' in get_text(nightbound).lower()
                            and nightbound != card
                        ):
                            options.append(nightbound)

                    if not options:
                        pass

                elif 'transform' in card_text:
                    for back in user_cards.values():
                        if (
                            'transform' in back['data']['version'].lower()
                            and back != card
                        ):
                            options.append(back)

                    if not options:
                        pass

            if options:
                options = [
                    option
                    for option in options
                    if get_card_name(option).split()[0]
                    == get_card_name(card).split()[0]
                ] or options

                options = [
                    option
                    for option in options
                    if option['data']['text']['pt']['text']
                    == card['data']['text']['reminder']['text']
                ] or options

                options = [
                    option
                    for option in options
                    if option['data']['text']['type']['text'].split('-')[0]
                    == card['data']['text']['type']['text'].split('-')[0]
                ] or options

                assert len(options) == 1
                dfcs[card['info']['id']] = options[0]['info']['id']

        for card in user_cards.values():
            set_name = add_set(sets, card)
            add_card(
                cards,
                card,
                set_name,
                user_cards,
                (
                    user_cards[dfcs[card['info']['id']]]
                    if card['info']['id'] in dfcs
                    else None
                ),
                card['info']['id'] in dfcs.values(),
                tokens,
            )

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


color_names = {'W': 'White', 'U': 'Blue', 'B': 'Black', 'R': 'Red', 'G': 'Green'}


if __name__ == '__main__':
    main()
