export const allowedMotions = new Set([
  "slow_push",
  "pan_left",
  "pan_right",
  "zoom_in",
  "zoom_out",
]);

export const validateRenderPayload = (payload) => {
  if (!payload || typeof payload !== "object") {
    throw new TypeError("render payload must be an object");
  }

  const fps = positiveInteger(payload.fps, "fps");
  const width = positiveInteger(payload.width, "width");
  const height = positiveInteger(payload.height, "height");
  const scenes = Array.isArray(payload.scenes) ? payload.scenes : [];
  if (scenes.length === 0) {
    throw new TypeError("render payload requires at least one scene");
  }

  const normalizedScenes = scenes.map((scene, index) => validateScene(scene, index));
  return {
    fps,
    width,
    height,
    audioPath: typeof payload.audioPath === "string" ? payload.audioPath : null,
    scenes: normalizedScenes,
  };
};

export const calculateDurationInFrames = (payload) => {
  return payload.scenes.reduce((maxFrame, scene) => {
    return Math.max(maxFrame, scene.startFrame + scene.durationInFrames);
  }, 0);
};

export const getSceneAtFrame = (payload, frame) => {
  return (
    payload.scenes.find((scene) => {
      return frame >= scene.startFrame && frame < scene.startFrame + scene.durationInFrames;
    }) ?? payload.scenes[payload.scenes.length - 1]
  );
};

const validateScene = (scene, index) => {
  if (!scene || typeof scene !== "object") {
    throw new TypeError(`scene ${index} must be an object`);
  }

  const motion = scene.motion ?? "slow_push";
  if (!allowedMotions.has(motion)) {
    throw new TypeError(`scene ${index} has unsupported motion ${motion}`);
  }

  const focalPoint = Array.isArray(scene.focalPoint) ? scene.focalPoint : [0.5, 0.5];
  if (focalPoint.length !== 2) {
    throw new TypeError(`scene ${index} focalPoint must have two values`);
  }

  return {
    sceneId: requiredString(scene.sceneId, `scene ${index} sceneId`),
    startFrame: nonNegativeInteger(scene.startFrame, `scene ${index} startFrame`),
    durationInFrames: positiveInteger(scene.durationInFrames, `scene ${index} durationInFrames`),
    imagePath: requiredString(scene.imagePath, `scene ${index} imagePath`),
    motion,
    focalPoint: focalPoint.map((value, pointIndex) => {
      if (typeof value !== "number" || value < 0 || value > 1) {
        throw new TypeError(`scene ${index} focalPoint ${pointIndex} must be between 0 and 1`);
      }
      return value;
    }),
  };
};

const requiredString = (value, name) => {
  if (typeof value !== "string" || value.trim() === "") {
    throw new TypeError(`${name} is required`);
  }
  return value;
};

const positiveInteger = (value, name) => {
  if (!Number.isInteger(value) || value <= 0) {
    throw new TypeError(`${name} must be a positive integer`);
  }
  return value;
};

const nonNegativeInteger = (value, name) => {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer`);
  }
  return value;
};
