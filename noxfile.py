import webbrowser

import nox

# TODO: @nox.parametrize on ordered set
@nox.session(python=["3.6", "3.7", "3.8", "pypy3"])
def tests(session):
    session.install(".")
    session.install("pytest==5.4.1")
    session.install("pytest-subtests==0.3.0")
    session.run("pytest")


@nox.session(python=["3.6"])
def lint(session):
    session.install(".")
    session.install("black==19.10b0")
    session.install("mypy==0.770")
    session.install("mypy-extensions==0.4.3")
    session.run("mypy")
    session.run("black", "src")


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
