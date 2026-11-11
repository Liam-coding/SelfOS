"""app / pipeline_api responsibilities."""


def api_summarizer(root, *, review_records=True):
    """Published prepared-session adapter used by the frozen live evaluation."""
    from selfos.providers.knowledge import api_summarizer as factory
    return factory(root,review_records=review_records)
