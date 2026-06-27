from app.hlhp.data.texture_map import get_textured_product
from app.hlhp.models.profile import SkinType


def test_textured_product_does_not_double_prefix_moisturizer_action():
    action = "Use a humectant-rich barrier-repair cream."
    result = get_textured_product("moisturizer", SkinType.DRY, action)
    assert not result.lower().startswith("rich cream a")
    assert "humectant-rich barrier-repair cream" in result.lower()
    assert "barrier-first finish" in result
