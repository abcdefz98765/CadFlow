import pytest

from ai_native_cad.features import (
    boss_with_hole,
    cylindrical_spacer,
    rectangular_corner_points,
    rectangular_shell,
)


def test_rectangular_corner_points():
    assert set(rectangular_corner_points(100, 60, 10)) == {
        (-40, -20),
        (-40, 20),
        (40, -20),
        (40, 20),
    }


def test_cylindrical_spacer_bbox():
    model = cylindrical_spacer(12, 6, 20)
    bbox = model.val().BoundingBox()

    assert bbox.xlen == pytest.approx(12, abs=0.1)
    assert bbox.ylen == pytest.approx(12, abs=0.1)
    assert bbox.zlen == pytest.approx(20, abs=0.1)
    assert model.val().Volume() > 0


def test_boss_with_hole_bbox_position():
    model = boss_with_hole(10, 4, 6, (20, -10), z_base=2)
    bbox = model.val().BoundingBox()

    assert bbox.xmin == pytest.approx(15, abs=0.1)
    assert bbox.xmax == pytest.approx(25, abs=0.1)
    assert bbox.ymin == pytest.approx(-15, abs=0.1)
    assert bbox.ymax == pytest.approx(-5, abs=0.1)
    assert bbox.zmin == pytest.approx(2, abs=0.1)
    assert bbox.zmax == pytest.approx(8, abs=0.1)


def test_rectangular_shell_bbox():
    model = rectangular_shell(100, 60, 25, 2)
    bbox = model.val().BoundingBox()

    assert bbox.xlen == pytest.approx(100, abs=0.1)
    assert bbox.ylen == pytest.approx(60, abs=0.1)
    assert bbox.zmin == pytest.approx(0, abs=0.1)
    assert bbox.zmax == pytest.approx(25, abs=0.1)
