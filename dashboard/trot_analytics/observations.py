"""Affichage en lecture seule des observations publiées dans le registre."""
from html import escape

from .dates import afficher_instant
from .usages import en_observation


def tableau_observations(rows, groupe):
    labels = groupe.libelles
    status = labels['ipr_statut']
    rank = labels['ipr_rang_shadow']
    fields = ('N°', 'Cheval', *labels.values())
    values = [row for row in rows if row.get(labels['ipr_version'])]
    if not values:
        return ''

    def order(row):
        nb = row.get(rank)
        return (nb if type(nb) in (int, float) and nb > 0 else float('inf'),
                str(row.get('N°', '')).zfill(2))

    def display(row, field):
        value = row.get(field)
        if field == labels['ipr_calcul_utc']:
            value = afficher_instant(value)
        if type(value) is float:
            value = f'{value:g}'.replace('.', ',')
        return '—' if value is None or value == '' else str(value)

    def text(value, italic):
        escaped = escape(value)
        return f'<em>{escaped}</em>' if italic else escaped

    observation = any(en_observation(row.get(status)) for row in values)
    headings = ''.join(
        f'<th scope="col">{text(field.removesuffix(" UTC") + " (Paris)" if field == labels["ipr_calcul_utc"] else field, observation and field in labels.values())}</th>'
        for field in fields)
    body = []
    for row in sorted(values, key=order):
        experimental = en_observation(row.get(status))
        cells = ''.join(f'<td>{text(display(row, field), experimental and field in labels.values())}</td>'
                        for field in fields)
        body.append(f'<tr>{cells}</tr>')
    legend = f'<p><em>{escape(groupe.usage)}</em></p>' if observation else ''
    return (legend + f'<div style="overflow-x:auto"><table aria-label="Indice de performance relative">'
            f'<thead><tr>{headings}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def tableau_geny(rows, context, groupe):
    fields = [*context, *groupe.libelles.values()]

    def cell(tag, value, italic):
        text = escape(str(value if value not in ('', None) else '—'))
        if italic:
            text = f'<em>{text}</em>'
        return f'<{tag}>{text}</{tag}>'

    heading = ''.join(cell('th', field, groupe.italique and field not in context) for field in fields)
    body = ''.join('<tr>' + ''.join(cell('td', row.get(field), groupe.italique and field not in context)
                                  for field in fields) + '</tr>' for row in rows)
    return (f'<div style="overflow-x:auto"><table aria-label="Historique Geny">'
            f'<thead><tr>{heading}</tr></thead><tbody>{body}</tbody></table></div>')
