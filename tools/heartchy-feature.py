"""Local work-document scaffolding and documentation contracts; no Git/runtime IO."""
import os
import posixpath
import re
from urllib.parse import unquote, urlsplit


SKILLS = (
    "feature-development", "core-config", "cli-command", "shell-ui",
    "service-development", "privileged-integration", "migration", "testing",
    "visual-verification", "upstream-compatibility", "release-preparation",
)
TEMPLATE = "work/FEATURE_TEMPLATE.md"
FIELDS = (
    "Objetivo", "No objetivos", "Decisiones de Diego aplicables", "Tipo de Feature",
    "Subsistemas afectados", "Integración con Omarchy", "APIs/contratos utilizados",
    "Persistencia", "Privilegios", "Dependencias", "Compatibilidad conocida",
    "Criterios de aceptación", "Pruebas requeridas", "Rollback / retirada",
    "Riesgos", "Decisiones pendientes de Diego", "Evidencia",
)


def template(read, require):
    text = read(TEMPLATE).decode("utf-8")
    fields = re.findall(r"^## (.+)$", text, re.M)
    require(len(fields) == len(set(fields)) and set(fields) == set(FIELDS),
            "feature template: missing, duplicate or unknown contract fields")
    parts = re.split(r"^## .+$", text, flags=re.M)
    require(all(part.strip() for part in parts[1:]), "feature template: empty contract field")
    pairs = re.findall(r"^([^\n:]+): ([^\n]+)$", parts[0], re.M)
    require(len(pairs) == len({key for key, _ in pairs}), "feature template: duplicate metadata")
    metadata = dict(pairs)
    require(metadata == {"ID": "HCY-{{slug}}", "Nombre": "{{name}}", "Estado": "DESIGN",
                         "Último estado alcanzado": "DESIGN", "Bloqueo": "N/A", "Responsable": "PENDIENTE"},
            "feature template: unsafe initial state or invalid metadata")
    require(set(re.findall(r"{{(.*?)}}", text)) == {"slug", "name"},
            "feature template: unknown placeholders")
    return text


def markdown_content(text):
    # This checker supports the repository's inline links, not all CommonMark.
    # Examples inside fenced code are not navigational references.
    return re.sub(r"(?ms)^```[^\n]*\n.*?^```[^\n]*$", "", text)


def anchors(text):
    result = set(re.findall(r'<a id="([^"]+)"></a>', text))
    for heading in re.findall(r"^#{1,6} (.+)$", markdown_content(text), re.M):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        result.add(slug)
    return result


def check(api):
    read, require = api["read_project"], api["require"]
    template(read, require)
    routes = read("AGENTS.md").decode("utf-8")
    linked = re.findall(r"\]\((agents/skills/[^\s)]+)\)", routes)
    required = {"agents/skills/" + name + ".md" for name in SKILLS}
    require(set(linked) == required and len(linked) == len(required),
            "AGENTS: skills routing must identify each supported guide once")
    for name in SKILLS:
        path = "agents/skills/" + name + ".md"
        text = read(path).decode("utf-8")
        front = re.match(r"\A---\nname: ([a-z-]+)\ndescription: ([^\n]+)\n---\n(.+)\Z", text, re.S)
        require(front is not None and front[1] == name and bool(front[2].strip()) and bool(front[3].strip()),
                path + ": missing purpose/trigger metadata or procedure")

    pending = {"README.md", "AGENTS.md", "STATUS.md", "docs/architecture.md", "docs/development.md",
               "docs/testing.md", "docs/upstream.md", "docs/upstream-contracts.md", TEMPLATE} | required
    visited = set()
    while pending:
        doc = pending.pop()
        if doc in visited:
            continue
        require(len(visited) < 150, "documentation graph exceeds review scope")
        visited.add(doc)
        text = read(doc).decode("utf-8")
        for target in re.findall(r"\]\(([^\s)]+)\)", markdown_content(text)):
            link = urlsplit(target)
            if link.scheme in ("https", "http"):
                continue
            require(not link.scheme and not link.netloc and not link.query,
                    f"{doc}: unsupported reference: {target}")
            path = unquote(link.path)
            require(not path.startswith("/") and "\\" not in path, f"{doc}: reference outside repo: {target}")
            relative = posixpath.normpath(posixpath.join(posixpath.dirname(doc), path)) if path else doc
            api["relative_parts"](relative)
            destination = read(relative)
            if link.fragment:
                require(relative.endswith(".md") and unquote(link.fragment) in anchors(destination.decode("utf-8")),
                        f"{doc}: broken anchor: {target}")
            if relative.endswith(".md"):
                pending.add(relative)
    return len(required), len(visited)


def new(api, slug):
    require = api["require"]
    require(len(slug) <= 64 and re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", slug),
            "invalid feature slug: lowercase ASCII letter, then letters/digits and single hyphens; max 64")
    text = template(api["read_project"], require)
    content = text.replace("{{slug}}", slug).replace("{{name}}", slug.replace("-", " ")).encode("utf-8")
    # Existing secure directory-FD writer: O_EXCL prevents overwrites, even a
    # dangling symlink; no-follow on every parent prevents directory escapes.
    root_fd = os.open(api["ROOT"], os.O_RDONLY | os.O_DIRECTORY | api["NOFOLLOW"])
    try:
        api["write_new"](root_fd, "work/features/" + slug + ".md", content)
    except OSError as exc:
        raise api["Invalid"]("feature refused/failed: " + str(exc) +
                             "; no overwrite or cleanup; inspect any partial document") from exc
    finally:
        os.close(root_fd)
    return "work/features/" + slug + ".md"
