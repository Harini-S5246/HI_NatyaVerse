def prepare_image(frame, size: tuple[int, int] = (224, 224)):
    import cv2
    import numpy as np
    if frame is None: raise ValueError("Frame is empty")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    # EfficientNet models contain their own Rescaling(1 / 255) input layer.
    return np.expand_dims(cv2.resize(rgb, size).astype("float32"), axis=0)
