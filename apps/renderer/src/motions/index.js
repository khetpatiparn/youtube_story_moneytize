export const getMotionStyle = (motion, frame, durationInFrames, focalPoint = [0.5, 0.5]) => {
  const progress = clamp(durationInFrames <= 0 ? 0 : frame / durationInFrames);
  const origin = `${Math.round(focalPoint[0] * 100)}% ${Math.round(focalPoint[1] * 100)}%`;

  if (motion === "pan_left") {
    return {
      transform: `scale(1.0400) translateX(${format(-4 * progress)}%)`,
      transformOrigin: origin,
    };
  }

  if (motion === "pan_right") {
    return {
      transform: `scale(1.0400) translateX(${format(4 * progress)}%)`,
      transformOrigin: origin,
    };
  }

  if (motion === "zoom_out") {
    return {
      transform: `scale(${format(1.08 - 0.08 * progress)})`,
      transformOrigin: origin,
    };
  }

  return {
    transform: `scale(${format(1 + 0.08 * progress)})`,
    transformOrigin: origin,
  };
};

const clamp = (value) => Math.max(0, Math.min(1, value));
const format = (value) => value.toFixed(4);
