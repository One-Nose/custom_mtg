import re
from random import choice, choices, sample
from xml.etree.ElementTree import Element, parse

from iteround import saferound  # type: ignore

with open('01.customcards.xml', encoding='utf-8') as file:
    xml = parse(file)

assert (cards := xml.find('cards')) is not None

commander_options: list[Element] = []
couple_options: list[tuple[Element, Element]] = []
partner_cards: list[Element] = []


def is_actual_card(card_element: Element) -> bool:
    if (token := card_element.find('token')) is not None and token.text == '1':
        return False

    assert (prop_element := card_element.find('prop')) is not None
    assert (side := prop_element.find('side')) is not None
    if side.text != 'front':
        return False

    return True


for card in cards.findall('card'):
    if not is_actual_card(card):
        continue

    assert (name := card.find('name')) is not None

    if any(
        (option_name := couple[1].find('name')) is not None
        and option_name.text == name.text
        for couple in couple_options
    ):
        continue

    assert (text := card.find('text')) is not None
    rulestext = (text.text or '').lower()

    assert (prop := card.find('prop')) is not None
    assert (cardtype := prop.find('type')) is not None

    types = (cardtype.text or '').partition('—')
    supertypes, subtypes = types[0].lower().split(), types[2].lower().split()

    if (
        'legendary' not in supertypes or not 'creature' in supertypes
    ) and ' can be your commander' not in rulestext:
        continue

    match = re.search(r'partner with ([^\n(]+)', rulestext)
    if match:
        should_continue: bool = False
        for partner in cards.findall('card'):
            assert (partner_name := partner.find('name')) is not None
            if (partner_name.text or '').lower() == match[1].strip():
                couple_options.append((card, partner))
                should_continue: bool = True
                break
        if should_continue:
            continue

    if 'partner' in rulestext:
        partner_cards.append(card)
        continue

    commander_options.append(card)

commander_type = choices(
    ('normal', 'partner_with', 'partner'),
    (len(commander_options), len(couple_options), len(partner_cards)),
)[0]

commanders: list[Element]
if commander_type == 'normal':
    commanders = [choice(commander_options)]
elif commander_type == 'partner_with':
    commanders = list(choice(couple_options))
elif commander_type == 'partner':
    commanders = sample(partner_cards, 2)
else:
    raise ValueError


color_identity: set[str] = set()
for commander in commanders:
    assert (prop := commander.find('prop')) is not None

    coloridentity = prop.find('coloridentity')
    if coloridentity is None or coloridentity.text is None:
        continue
    color_identity |= set(coloridentity.text)


legal_cards: list[Element] = []
for card in cards.findall('card'):
    if not is_actual_card(card):
        continue

    if card in commanders:
        continue

    assert (prop := card.find('prop')) is not None
    if (
        (coloridentity := prop.find('coloridentity')) is not None
        and coloridentity.text is not None
        and any(color not in color_identity for color in coloridentity.text)
    ):
        continue

    legal_cards.append(card)

for commander in commanders:
    assert (name := commander.find('name')) is not None
    print(name.text)
print(color_identity)
print(len(legal_cards))

chosen_cards = sample(legal_cards, 60 - len(commanders))

mana: dict[str, float] = {'W': 0, 'U': 0, 'B': 0, 'R': 0, 'G': 0, 'C': 0}
for card in chosen_cards:
    assert (prop := card.find('prop')) is not None

    manacost = prop.find('manacost')
    if manacost is None or manacost.text is None:
        continue

    for color in mana:
        mana[color] += manacost.text.count(color)

print(mana)

lands: int = 0
for card in chosen_cards:
    assert (prop := card.find('prop')) is not None
    assert (card_type := prop.find('type')) is not None

    if 'land' in (card_type.text or '').lower().split():
        coloridentity = prop.find('coloridentity')

        for color in (coloridentity.text or '') if coloridentity is not None else '':
            lands += 1
            mana[color] -= 1

print(lands)
print(mana)

ratio = 40 / sum(mana.values())

print(ratio)

for color in mana:
    mana[color] *= ratio

print(mana)

mana = saferound(mana, 0)  # type: ignore

print(mana)

deck_string: str = '// Commander Zone\n'

for commander in commanders:
    assert (name := commander.find('name')) is not None
    deck_string += f'SB: 1 {name.text}\n'

deck_string += f'\n// {60 - len(commanders)} Custom Cards\n'

for card in chosen_cards:
    assert (name := card.find('name')) is not None
    deck_string += f'1 {name.text}\n'

deck_string += '\n// 40 Basic Lands\n'

basic_lands = {
    'W': 'Plains',
    'U': 'Island',
    'B': 'Swamp',
    'R': 'Mountain',
    'G': 'Forest',
    'C': 'Wastes',
}

for color, amount in mana.items():
    if amount == 0:
        continue
    deck_string += f'{amount:.0f} {basic_lands[color]}\n'

with open('deck.dec', 'w', encoding='utf-8') as file:
    file.write(deck_string)
