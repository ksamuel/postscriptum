"""Exception classes specific to postscriptum
"""


class ExitFromSignal(SystemExit):
    """ SystemExit child we raise when we want to exit form signals

        This is done to catch it specifically later and deal with this exit
        as a special case.
    """

    pass
