"""Position assignée au départ et provenance des observations PMU et Geny."""
import re
from .selection_metier_v20_4 import normaliser, normaliser_hippodrome

FAQ_PMU = ('https://www.pmu.fr/turf/faq/culture-des-courses-et-paris-hippiques/'
           'comment-fonctionne-autostart-course-hippique/')
CAPACITES_PAR_PARCOURS = {
    ('vincennes', 2100): 9,
    ('cabourg', 2725): 7,
}


def mode_explicite(raw):
    label = normaliser(raw)
    if label in ('autostart', 'auto'):
        return 'Autostart'
    if label in ('volte', 'voltee', 'elastique'):
        return 'Volté'
    return ''


def mode_pmu(course):
    params = course.get('parametres_pmu') or {}
    for field in ('typeDepart', 'categorieParticularite'):
        mode = mode_explicite(params.get(field))
        if mode:
            return mode, field
    conditions = normaliser(params.get('conditions'))
    if re.search(r'\bdepart a l autostart\b', conditions):
        return 'Autostart', 'conditions'
    if re.search(r'\bdepart (?:a la volte|volte)\b', conditions):
        return 'Volté', 'conditions'
    return '', ''


def entier(value, minimum=1, maximum=5000):
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 4:
        value = int(value)
    return value if type(value) is int and minimum <= value <= maximum else None


def depart_partant_pmu(course, participant):
    mode, champ = mode_pmu(course)
    params = course.get('parametres_pmu') or {}
    distance = entier(course.get('distance_m'))
    details = {}
    if mode:
        details.update(mode=mode, champ_mode=champ)
    if mode == 'Autostart':
        position = entier(participant.get('placeCorde'), maximum=18)
        course_capacity = re.search(r'\b(\d{1,2})\s+au\s+(?:1er|premier)\s+rang\b',
                                    normaliser(params.get('conditions')))
        capacity = (entier(course_capacity.group(1), maximum=9) if course_capacity
                    else CAPACITES_PAR_PARCOURS.get((normaliser_hippodrome(course.get('hippodrome')), distance)))
        if capacity:
            details.update(capacite=capacity, source_capacite='PMU_PROGRAMME_CONDITIONS' if course_capacity else FAQ_PMU)
        if position is not None:
            details.update(position=position, champ_position='placeCorde')
            if capacity and position <= 2 * capacity:
                details['ligne'] = 1 if position <= capacity else 2
    handicap = entier(participant.get('handicapDistance'))
    if distance and handicap and handicap >= distance and mode != 'Autostart':
        details.update(recul_m=handicap - distance, champ_recul='handicapDistance')
    return details


def depart_historique_geny(course, participation):
    mode = mode_explicite(course.get('depart'))
    values = {'mode': mode} if mode else {}
    position = entier(participation.get('positionDepart'), maximum=18)
    if mode == 'Autostart' and position is not None:
        values['position'] = position
    return values
