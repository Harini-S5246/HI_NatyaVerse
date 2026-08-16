from app.config import settings


def test_default_configuration_has_safe_local_directories():
    assert settings.upload_dir.name == "uploads"
    assert settings.frame_output_dir.name == "frames"
    assert settings.results_dir.name == "results"
    assert settings.mudra_model_path.name == "Natya_Mudra_EfficientNetB0_FineTuned.keras"
    assert settings.pose_model_path.name == "Natya_Pose_BiLSTM_Best.keras"
    assert settings.bhava_model_path.name == "bhava_phase3_moderated_best.keras"
