declare module '@mkkellogg/gaussian-splats-3d' {
    import * as THREE from 'three';

    // WebXR Mode enum
    export enum WebXRMode {
        None = 0,
        VR = 1,
        AR = 2
    }

    export interface ViewerOptions {
        cameraUp?: [number, number, number];
        initialCameraPosition?: [number, number, number];
        rootElement: HTMLElement;
        gpuAcceleratedSort?: boolean;
        sharedMemoryForWorkers?: boolean;
        useBuiltInControls?: boolean;
        selfDrivenMode?: boolean;
        ignoreDevicePixelRatio?: boolean;
        dynamicLoading?: boolean;
        webXRMode?: WebXRMode;
        [key: string]: any;
    }

    export interface Controls {
        mouseButtons: {
            LEFT: any;
            MIDDLE: any;
            RIGHT: any;
        } | null;
        touches: {
            ONE: any;
            TWO: any;
        } | null;
        keys?: {
            LEFT: string;
            UP: string;
            RIGHT: string;
            BOTTOM: string;
        };
        enableKeys?: boolean;
        listenToKeyEvents?: (el: any) => void;
        
        rotateSpeed: number;
        panSpeed: number;
        zoomSpeed: number;
        keyPanSpeed?: number;
        
        enableDamping: boolean;
        dampingFactor: number;
        
        autoRotate: boolean;
        autoRotateSpeed: number;
        
        minDistance: number;
        maxDistance: number;
        
        minAzimuthAngle: number;
        maxAzimuthAngle: number;
        minPolarAngle: number;
        maxPolarAngle: number;

        target: THREE.Vector3;
        
        update: () => void;
        reset: () => void;
    }

    export class Viewer {
        constructor(options: ViewerOptions);
        
        addSplatScene(url: string, options?: any): Promise<void>;
        getSplatSceneCount(): number;
        removeSplatScene(index: number): void;
        
        dispose(): void;
        start(): void;
        stop(): void;
        update(): void;
        render(): void;
        
        camera: THREE.Camera;
        cameraControls: Controls; // It might be cameraControls OR controls depending on version/config
        controls: Controls;       // Fallback
        content: THREE.Group;
        renderer: THREE.WebGLRenderer;
    }
}
