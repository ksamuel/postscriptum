import webbrowser

import nox


@nox.session(python=["3.6", "3.7", "3.8"])
def tests(session):
    session.install(".")
    session.install("-r", "dev-requirements.txt")
    session.run("pytest")


@nox.session(python="3.7")
def coverage(session):
    session.install(".")
    session.install("-r", "dev-requirements.txt")
    session.run("coverage", "run", "-m", "pytest")
    action = session.posargs[0] if session.posargs else "report"
    if action == "browse":
        session.run("coverage", "html")
        webbrowser.open_new_tab("./build/coverage_html_report/index.html")
    else:
        session.run("coverage", action)
