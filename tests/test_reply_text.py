from types import SimpleNamespace as NS

from tomoshibi.llm import ReplyText, restates


def blocks(*parts):
    """Stream events for a list of blocks: a string is a text block, ("cited", text) a text
    block with citations, any other tuple a non-text block of that type."""
    events = []
    for i, part in enumerate(parts):
        if isinstance(part, str):
            block, text = NS(type="text", citations=None), part
        elif part[0] == "cited":
            block, text = NS(type="text", citations=[]), part[1]
        else:
            block, text = NS(type=part[0]), None
        events.append(NS(type="content_block_start", index=i, content_block=block))
        if block.type == "text" and block.citations is not None:
            events.append(NS(type="content_block_delta", index=i,
                             delta=NS(type="citations_delta", citation=NS(type="web_search_result_location"))))
        for k in range(0, len(text or ""), 7):  # streamed in small pieces, mid-word
            events.append(NS(type="content_block_delta", index=i, delta=NS(type="text_delta", text=text[k:k + 7])))
        events.append(NS(type="content_block_stop", index=i))
    return events


def spoken(events):
    reply = ReplyText()
    return "".join(piece for event in events for piece in reply.feed(event))


SEARCH = (("thinking",), ("server_tool_use",), ("web_search_tool_result",), ("thinking",))


def test_a_quote_restating_the_sentence_before_it_is_not_spoken():
    # Recorded from "When are the elections in Naples, Florida?" (2026-10-22).
    events = blocks("Let me check that for you.", *SEARCH,
                    "The next election is on Tuesday, November 3, 2026. ",
                    ("cited", "The 2026 election is Tuesday, Nov. 3, 2026."),
                    " Early voting runs ",
                    ("cited", "from 9 a.m. to 6 p.m., Oct. 22 through Oct. 31"),
                    ", so you can vote early.")
    assert spoken(events) == ("Let me check that for you. The next election is on Tuesday, November 3, 2026. "
                              " Early voting runs from 9 a.m. to 6 p.m., Oct. 22 through Oct. 31, so you can vote early.")


def test_quotes_that_add_something_are_spoken_and_blocks_join_as_they_are():
    events = blocks(*SEARCH, "Here is what's on. The Naples Zoo has ",
                    ("cited", "spooky fun from 9 a.m. to 4:30 p.m., Oct. 24-26."), " ",
                    ("cited", "The Stone Crab Festival is at Tin City, Oct. 23-25."))
    assert spoken(events) == ("Here is what's on. The Naples Zoo has spooky fun from 9 a.m. to 4:30 p.m., "
                              "Oct. 24-26. The Stone Crab Festival is at Tin City, Oct. 23-25.")


def test_let_me_check_is_spoken_before_the_search_and_a_tool_round_adds_one_space():
    reply = ReplyText()
    first = [p for e in blocks("Let me check.", ("tool_use",)) for p in reply.feed(e)]
    assert "".join(first) == "Let me check."  # streamed straight away, not held
    second = [p for e in blocks("It's sunny.") for p in reply.feed(e)]
    assert "".join(second) == " It's sunny."


def test_restates_needs_a_whole_sentence_with_only_numbers_already_said():
    said = "The next election is on Tuesday, November 3, 2026. "
    assert restates("The 2026 election is Tuesday, Nov. 3, 2026.", said)
    assert not restates("Early voting runs Oct. 22 through Oct. 31.", said)
    assert not restates("Early voting dates are subject to change.", said)  # nothing to compare
    assert not restates("from Nov. 3, 2026", said)  # finishes a sentence
    assert not restates("The 2026 election is Nov. 3.", "The next election is on Tuesday, November 3, ")
