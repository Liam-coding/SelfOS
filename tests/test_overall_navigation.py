from html.parser import HTMLParser

from selfos.web.rendering.dashboard import generate_dashboard


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_overall_has_native_keyboard_navigation_to_dimension_cards(tmp_path):
    vault = tmp_path / 'vault'
    vault.mkdir()
    html = generate_dashboard(vault).read_text(encoding='utf-8')
    elements = Elements(html).elements
    links = [attrs for tag, attrs in elements
             if tag == 'a' and 'knowledge-overall' in attrs.get('class', '').split()]
    assert len(links) == 1, 'Overall must be a native link, usable by keyboard'
    link = links[0]
    assert link['aria-labelledby'] == 'overall-title'
    target_id = link['href'].removeprefix('#')
    assert link['href'].startswith('#') and target_id
    targets = [(tag, attrs) for tag, attrs in elements if attrs.get('id') == target_id]
    assert len(targets) == 1
    _, target = targets[0]
    assert 'grid' in target.get('class', '').split()
    assert target['tabindex'] == '-1', 'Anchor destination must receive navigation focus'
