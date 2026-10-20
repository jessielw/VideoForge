from videoforge.core.video.vfr import fits, normalize


def test_zero_origin_keeps_fractional_intervals_and_last_end(tmp_path):
    source, output = tmp_path / "source.txt", tmp_path / "timestamps.txt"
    source.write_text("# timestamp format v2\n500.125\n541.833333\n575.2\n608.566666\n", encoding="utf-8")
    normalize(source, output)
    assert output.read_text().splitlines()[1:] == ["0.000", "41.708333", "75.075", "108.441666"]
    assert fits(output, 3)
