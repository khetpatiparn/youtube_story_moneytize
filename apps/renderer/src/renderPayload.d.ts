export type RenderScene = {
  sceneId: string;
  startFrame: number;
  durationInFrames: number;
  imagePath: string;
  motion: string;
  focalPoint: [number, number];
};

export type RenderPayload = {
  fps: number;
  width: number;
  height: number;
  audioPath: string | null;
  scenes: RenderScene[];
};

export declare const validateRenderPayload: (payload: unknown) => RenderPayload;
export declare const calculateDurationInFrames: (payload: RenderPayload) => number;
export declare const getSceneAtFrame: (payload: RenderPayload, frame: number) => RenderScene;
