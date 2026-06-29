import React from "react";
import {
  AbsoluteFill,
  Audio,
  Composition,
  Img,
  Sequence,
  staticFile,
  registerRoot,
  useCurrentFrame,
} from "remotion";

import renderPayload from "../sample/render_payload.json";
import {calculateDurationInFrames, validateRenderPayload} from "./renderPayload.js";
import {getMotionStyle} from "./motions/index.js";

type RenderScene = {
  sceneId: string;
  startFrame: number;
  durationInFrames: number;
  imagePath: string;
  motion: string;
  focalPoint: [number, number];
};

type RenderPayload = {
  fps: number;
  width: number;
  height: number;
  audioPath: string | null;
  scenes: RenderScene[];
};

export const StoryScene: React.FC<{scene: RenderScene}> = ({scene}) => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{backgroundColor: "#111827", overflow: "hidden"}}>
      <Img
        src={staticFile(scene.imagePath)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          ...getMotionStyle(scene.motion, frame, scene.durationInFrames, scene.focalPoint),
        }}
      />
    </AbsoluteFill>
  );
};

export const StoryVideo: React.FC<RenderPayload> = ({scenes, audioPath}) => {
  return (
    <AbsoluteFill style={{backgroundColor: "#111827"}}>
      {audioPath ? <Audio src={staticFile(audioPath)} /> : null}
      {scenes.map((scene) => (
        <Sequence
          key={scene.sceneId}
          from={scene.startFrame}
          durationInFrames={scene.durationInFrames}
        >
          <StoryScene scene={scene} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="YouTubeStory"
      component={StoryVideo}
      width={renderPayload.width}
      height={renderPayload.height}
      fps={renderPayload.fps}
      durationInFrames={calculateDurationInFrames(validateRenderPayload(renderPayload))}
      defaultProps={renderPayload}
      calculateMetadata={({props}) => {
        const payload = validateRenderPayload(props);
        return {
          durationInFrames: calculateDurationInFrames(payload),
          fps: payload.fps,
          width: payload.width,
          height: payload.height,
          props: payload,
        };
      }}
    />
  );
};

registerRoot(RemotionRoot);
