"""
Het GitHub-bord uitlezen
========================
Haalt één momentopname van een GitHub Project (v2) op via de GraphQL-API:

  * de iteraties van het iteratieveld (SPRINT_VELD, op bord 13 `WEEK`),
    lopend én afgesloten
  * alle items met hun huidige iteratie en Status

GitHub geeft via de API alleen de *huidige* waarde van een veld terug, niet
wat er eerder stond. Daarom bewaart deze app elke dag een momentopname
(zie opslag.py); de geschiedenis bestaat alleen in die momentopnamen.
"""

import requests

API = 'https://api.github.com/graphql'
PAGINA = 100  # het maximum dat GitHub per keer teruggeeft

VELD_QUERY = """
query($org: String!, $nummer: Int!, $sprint: String!) {
  organization(login: $org) {
    projectV2(number: $nummer) {
      id
      title
      url
      sprint: field(name: $sprint) {
        __typename
        ... on ProjectV2IterationField {
          configuration {
            iterations { id title startDate duration }
            completedIterations { id title startDate duration }
          }
        }
      }
    }
  }
}
"""

ITEMS_QUERY = """
query($org: String!, $nummer: Int!, $sprint: String!, $status: String!, $na: String) {
  organization(login: $org) {
    projectV2(number: $nummer) {
      items(first: %d, after: $na) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          type
          isArchived
          content {
            __typename
            ... on Issue { number title url state repository { nameWithOwner } }
            ... on PullRequest { number title url state repository { nameWithOwner } }
            ... on DraftIssue { title }
          }
          sprint: fieldValueByName(name: $sprint) {
            ... on ProjectV2ItemFieldIterationValue { iterationId title startDate duration }
          }
          status: fieldValueByName(name: $status) {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
        }
      }
    }
  }
}
""" % PAGINA


class GitHubFout(Exception):
    """Een fout die we in de interface laten zien, in gewone taal."""


def _vraag(token, query, variabelen):
    try:
        antwoord = requests.post(
            API,
            json={'query': query, 'variables': variabelen},
            headers={
                'Authorization': f'Bearer {token}',
                'User-Agent': 'AVX-AI-PROJECTS-INSIGHTS',
            },
            timeout=30,
        )
    except requests.RequestException as fout:
        raise GitHubFout(f'GitHub niet bereikbaar: {fout}') from fout

    if antwoord.status_code == 401:
        raise GitHubFout('GitHub weigert het token (401). Verlopen, ingetrokken of '
                         'nog niet goedgekeurd door de organisatie?')
    if antwoord.status_code != 200:
        raise GitHubFout(f'GitHub gaf status {antwoord.status_code}: {antwoord.text[:300]}')

    data = antwoord.json()
    if data.get('errors'):
        meldingen = '; '.join(fout.get('message', '?') for fout in data['errors'])
        raise GitHubFout(f'GitHub meldt: {meldingen}')
    return data['data']


def _project(data, org, nummer):
    project = ((data or {}).get('organization') or {}).get('projectV2')
    if not project:
        raise GitHubFout(f'Bord {org}/projects/{nummer} niet gevonden, of het token '
                         'heeft er geen leesrecht op.')
    return project


def _iteratie(waarde):
    return {
        'iteratie_id': waarde['id'] if 'id' in waarde else waarde['iterationId'],
        'titel': waarde['title'],
        'startdatum': waarde['startDate'],
        'duur_dagen': int(waarde['duration']),
    }


def _item(node):
    inhoud = node.get('content') or {}
    sprint = node.get('sprint') or {}
    status = node.get('status') or {}
    return {
        'item_id': node['id'],
        'soort': node.get('type'),
        'nummer': inhoud.get('number'),
        # REDACTED: het item verwijst naar een repo waar het token niet bij mag.
        'titel': inhoud.get('title') or '(geen toegang tot dit item)',
        'url': inhoud.get('url'),
        'repo': (inhoud.get('repository') or {}).get('nameWithOwner'),
        'staat': inhoud.get('state'),
        'status': status.get('name'),
        'iteratie': _iteratie(sprint) if sprint.get('iterationId') else None,
        'gearchiveerd': bool(node.get('isArchived')),
    }


def haal_bord(token, org, nummer, sprint_veld, status_veld):
    """Het hele bord in één keer: project, iteraties en items."""
    if not token:
        raise GitHubFout('Er staat geen GITHUB_TOKEN in de .env.')

    basis = {'org': org, 'nummer': int(nummer), 'sprint': sprint_veld}
    onbekend_veld = (f'Het veld "{sprint_veld}" bestaat niet op dit bord, of het is '
                     'geen iteratieveld. Controleer SPRINT_VELD in de .env.')
    try:
        project = _project(_vraag(token, VELD_QUERY, basis), org, nummer)
    except GitHubFout as fout:
        # GitHub zegt dan: "Could not resolve to a Unions::ProjectV2FieldConfiguration with the name ..."
        if 'ProjectV2FieldConfiguration' in str(fout):
            raise GitHubFout(onbekend_veld) from fout
        raise

    veld = project.get('sprint') or {}
    if veld.get('__typename') != 'ProjectV2IterationField':
        raise GitHubFout(onbekend_veld)
    configuratie = veld['configuration']
    iteraties = [_iteratie(i) for i in configuratie['iterations'] + configuratie['completedIterations']]

    items, na = [], None
    while True:
        data = _vraag(token, ITEMS_QUERY, {**basis, 'status': status_veld, 'na': na})
        pagina = _project(data, org, nummer)['items']
        items.extend(_item(node) for node in pagina['nodes'])
        if not pagina['pageInfo']['hasNextPage']:
            break
        na = pagina['pageInfo']['endCursor']

    return {
        'project_id': project['id'],
        'titel': project['title'],
        'url': project['url'],
        'iteraties': iteraties,
        'items': items,
    }


STATUS_GESCHIEDENIS_QUERY = """
query($id: ID!) {
  node(id: $id) {
    ... on ProjectV2Item {
      createdAt
      content {
        ... on Issue {
          timelineItems(first: 100, itemTypes: [PROJECT_V2_ITEM_STATUS_CHANGED_EVENT]) {
            nodes { ... on ProjectV2ItemStatusChangedEvent { createdAt status } }
          }
        }
        ... on PullRequest {
          timelineItems(first: 100, itemTypes: [PROJECT_V2_ITEM_STATUS_CHANGED_EVENT]) {
            nodes { ... on ProjectV2ItemStatusChangedEvent { createdAt status } }
          }
        }
      }
    }
  }
}
"""


def status_geschiedenis(token, item_id):
    """Wanneer het item op het bord kwam, en elke statuswijziging daarna.

    Geeft (op_bord_sinds, [(moment, status), ...]) terug, met ISO-tijden in UTC.
    GitHub bewaart dit wel voor de Status, maar niet voor een iteratieveld; zie
    reconstructie.py voor wat dat betekent.
    """
    node = _vraag(token, STATUS_GESCHIEDENIS_QUERY, {'id': item_id}).get('node')
    if not node:
        raise GitHubFout(f'Item {item_id} niet gevonden op GitHub.')
    inhoud = node.get('content') or {}
    gebeurtenissen = ((inhoud.get('timelineItems') or {}).get('nodes')) or []
    return node['createdAt'], sorted((g['createdAt'], g['status']) for g in gebeurtenissen if g)
