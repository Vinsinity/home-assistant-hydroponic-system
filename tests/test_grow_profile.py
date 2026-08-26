"""Tests for the simple grow-system and generate-only assistant models."""

import importlib.util
from pathlib import Path
import sys


MODULE = Path(__file__).parents[1] / "custom_components/hydroponic_system/grow_profile.py"
SPEC = importlib.util.spec_from_file_location("grow_profile", MODULE)
grow_profile = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = grow_profile
SPEC.loader.exec_module(grow_profile)


def test_system_profile_is_complete_bounded_and_copy_safe():
    profile = grow_profile.normalize_system_profile(
        {
            "cabin": {
                "name": "Main cabinet",
                "width_cm": "120",
                "depth_cm": 120,
                "height_cm": 200,
            },
            "system": {
                "growing_method": "RDWC",
                "reservoir_volume_l": 80,
                "system_volume_l": 140,
                "plant_capacity": 4,
            },
            "lighting": {
                "brand": "Lumatek",
                "model": "ZEUS",
                "power_w_each": 600,
                "dimmer_percent": 150,
                "schedule_on": "25:90",
            },
        }
    )

    assert profile["cabin"]["width_cm"] == 120
    assert profile["lighting"]["dimmer_percent"] == 100
    assert profile["lighting"]["schedule_on"] == "06:00"
    assert grow_profile.system_profile_completeness(profile)["complete"] is True


def test_assistant_settings_always_remain_read_only():
    settings = grow_profile.normalize_assistant_settings(
        {
            "provider_entity_id": "ai_task.claude",
            "history_hours": 168,
            "detail_level": "detailed",
            "read_only": False,
        }
    )

    assert settings["provider_entity_id"] == "ai_task.claude"
    assert settings["history_hours"] == 168
    assert settings["read_only"] is True
    assert grow_profile.normalize_assistant_settings(
        {"provider_entity_id": "conversation.unsafe"}
    )["provider_entity_id"] == ""


def test_assistant_prompt_marks_user_data_and_forbids_actions():
    prompt = grow_profile.build_assistant_prompt(
        cultivation={
            "active": True,
            "name": "Grow 1",
            "start_date": "2026-08-26",
            "identity": {"plant_species": "Tomato"},
            "plant_profile_snapshot": {
                "id": "tomato",
                "profile": {"kind": "editable_example"},
            },
            "system_snapshot": {},
        },
        active_stage="germination",
        active_profile={"ph": 5.8},
        system_profile={},
        sensor_summaries=[
            {"metric": "pH", "current": 5.9, "minimum": 5.7, "maximum": 6.1}
        ],
        recent_events=[
            {"local_date": "2026-08-26", "type": "user_note", "note": "Roots visible"}
        ],
        settings={"language": "tr"},
    )

    assert "salt-okunur" in prompt
    assert "hiçbir cihazı kontrol etme" in prompt
    assert "GROW_DATA_BEGIN" in prompt
    assert "Roots visible" in prompt
    assert '"id": "tomato"' in prompt


def test_context_summary_reports_missing_data_plainly():
    summary = grow_profile.assistant_context_summary(
        cultivation=None,
        system_profile={},
        sensor_summaries=[],
        recent_events=[],
    )

    assert summary["ready"] is False
    assert summary["missing"] == [
        "Aktif yetiştirme",
        "Kabin / sistem / ışık bilgileri",
        "Sensör geçmişi",
        "Günlük kaydı",
    ]
