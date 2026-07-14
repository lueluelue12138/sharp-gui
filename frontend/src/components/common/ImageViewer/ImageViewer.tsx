import { useCallback, useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { convertPhotosToModels } from '@/api';
import { useAppStore } from '@/store/useAppStore';
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  DownloadIcon,
  ExitFullscreenIcon,
  FullscreenIcon,
  PauseIcon,
  PlayIcon,
  SparklesIcon,
  VolumeIcon,
  VolumeMutedIcon,
} from '@/components/common/Icons';
import {
  createChromeSafePhotoPreviewUrl,
  shouldUseChromeSafePhotoPreview,
} from '@/utils/ultraHdrPreview';
import { getGallerySourceVideoUrl } from '@/utils/gallery';
import styles from './ImageViewer.module.css';

const VIDEO_LONG_PRESS_MS = 260;
const VIDEO_SCRUB_THRESHOLD_PX = 12;
const VIDEO_FINE_SCRUB_SECONDS_PER_PX = 0.08;
const VIDEO_CONTROLS_HIDE_DELAY_MS = 2200;
const VIDEO_VIEWER_HEIGHT_VH = 70;
const VIDEO_FALLBACK_ASPECT_RATIO = 16 / 9;
const VIDEO_KEYBOARD_SEEK_SECONDS = 5;
const VIDEO_KEYBOARD_FAST_SEEK_SECONDS = 15;
const VIDEO_KEYBOARD_VOLUME_STEP = 0.05;
const VIDEO_INLINE_PLAYBACK_ATTRIBUTES = {
  playsInline: true,
  'webkit-playsinline': 'true',
  'x5-video-player-type': 'h5-page',
  'x-webkit-airplay': 'deny',
  controlsList: 'nodownload noremoteplayback',
  disablePictureInPicture: true,
  disableRemotePlayback: true,
} as const;

interface LockableScreenOrientation extends ScreenOrientation {
  lock?: (orientation: OrientationLockType) => Promise<void>;
}

type OrientationLockType = 'any' | 'natural' | 'landscape' | 'portrait' | 'portrait-primary' | 'portrait-secondary' | 'landscape-primary' | 'landscape-secondary';

function getScreenOrientation(): LockableScreenOrientation | null {
  if (typeof screen === 'undefined') {
    return null;
  }

  return screen.orientation as LockableScreenOrientation | undefined ?? null;
}

async function lockScreenLandscape(): Promise<boolean> {
  const orientation = getScreenOrientation();
  if (!orientation?.lock) {
    return false;
  }

  try {
    await orientation.lock('landscape');
    return true;
  } catch {
    return false;
  }
}

function unlockScreenOrientation(): void {
  try {
    getScreenOrientation()?.unlock();
  } catch {
    // Some browsers expose the API but reject unlock outside their allowed state.
  }
}

export function ImageViewer() {
  const {
    previewImage,
    previewPhoto,
    photoItems,
    setPreviewImage,
    setPreviewPhoto,
    openVideoReconstructionDialog,
    upsertTasks,
  } = useAppStore();
  const { t } = useTranslation();
  
  const [isClosing, setIsClosing] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isConverting, setIsConverting] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [chromeSafeImage, setChromeSafeImage] = useState<{ sourceUrl: string; objectUrl: string } | null>(null);
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; message: string } | null>(null);
  const [isVideoPlaying, setIsVideoPlaying] = useState(false);
  const [videoDuration, setVideoDuration] = useState(0);
  const [videoCurrentTime, setVideoCurrentTime] = useState(0);
  const [videoVolume, setVideoVolume] = useState(1);
  const [videoMuted, setVideoMuted] = useState(false);
  const [videoError, setVideoError] = useState(false);
  const [isVideoScrubbing, setIsVideoScrubbing] = useState(false);
  const [videoScrubLabel, setVideoScrubLabel] = useState<string | null>(null);
  const [videoControlsVisible, setVideoControlsVisible] = useState(true);
  const [isVideoFullscreen, setIsVideoFullscreen] = useState(false);
  const [isLandscapeVideo, setIsLandscapeVideo] = useState(false);
  const [videoNaturalSize, setVideoNaturalSize] = useState<{ width: number; height: number } | null>(null);
  
  const overlayRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const videoStageRef = useRef<HTMLDivElement | null>(null);
  const videoLongPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const videoControlsHideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const videoOrientationLocked = useRef(false);
  const videoScrubRef = useRef<{
    startX: number;
    startY: number;
    baseTime: number;
    targetTime: number;
    wasPlaying: boolean;
    isTouchLike: boolean;
    activated: boolean;
    cancelled: boolean;
  } | null>(null);

  // --- Zoom & Pan State ---
  const [transform, setTransform] = useState({ scale: 1, x: 0, y: 0 });
  const { scale, x, y } = transform;
  const [isDragging, setIsDragging] = useState(false);
  const [isPinching, setIsPinching] = useState(false);
  const isMoved = useRef(false); // To track if we dragged vs just clicked
  const startPos = useRef({ x: 0, y: 0, posX: 0, posY: 0, dist: 0, scale: 1 });
  const wheelTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activePreview = previewPhoto ?? previewImage;
  const isPhotoPreview = Boolean(previewPhoto);
  const sourceVideoUrl = previewImage ? getGallerySourceVideoUrl(previewImage) : null;
  const isSourceVideoPreview = !previewPhoto
    && Boolean(sourceVideoUrl);
  const isVideoPreview = previewPhoto?.media_type === 'video' || isSourceVideoPreview;
  const activeName = previewPhoto?.name ?? previewImage?.source_name ?? previewImage?.name ?? '';
  const rawImageUrl = activePreview && !isVideoPreview
    ? previewPhoto
      ? (previewPhoto.full_url ?? previewPhoto.preview_url)
      : `/api/original/${encodeURIComponent(previewImage?.id ?? '')}`
    : null;
  const shouldUseSafePhotoPreview = shouldUseChromeSafePhotoPreview(rawImageUrl, activeName);

  const releaseVideoOrientationLock = useCallback(() => {
    if (!videoOrientationLocked.current) {
      return;
    }

    videoOrientationLocked.current = false;
    unlockScreenOrientation();
  }, []);

  const handleClose = useCallback(() => {
    releaseVideoOrientationLock();
    setIsClosing(true);
    // Wait for the exit animation to finish
    setTimeout(() => {
      if (isPhotoPreview) {
        setPreviewPhoto(null);
      } else {
        setPreviewImage(null);
      }
      setIsClosing(false);
    }, 250);
  }, [isPhotoPreview, releaseVideoOrientationLock, setPreviewImage, setPreviewPhoto]);

  // Handle Escape key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && activePreview) {
        handleClose();
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activePreview, handleClose]);

  // Lock body scroll and reset states when opened
  useEffect(() => {
    if (activePreview) {
      document.body.style.overflow = 'hidden';
      setIsLoaded(false);
      setIsClosing(false);
      setIsDownloading(false);
      setIsConverting(false);
      setImageError(false);
      setNotice(null);
      setIsVideoPlaying(false);
      setVideoDuration(0);
      setVideoCurrentTime(0);
      setVideoVolume(1);
      setVideoMuted(false);
      setVideoError(false);
      setIsVideoScrubbing(false);
      setVideoScrubLabel(null);
      setVideoControlsVisible(true);
      setIsLandscapeVideo(false);
      setVideoNaturalSize(null);
      setTransform({ scale: 1, x: 0, y: 0 });
    } else {
      releaseVideoOrientationLock();
      document.body.style.overflow = '';
    }
    return () => {
      releaseVideoOrientationLock();
      document.body.style.overflow = '';
    };
  }, [activePreview, releaseVideoOrientationLock]);

  useEffect(() => {
    if (!activePreview) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      overlayRef.current?.focus({ preventScroll: true });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [activePreview]);


  useEffect(() => {
    const video = videoRef.current;
    if (!video || !isVideoPreview) {
      return;
    }

    video.volume = videoVolume;
    video.muted = videoMuted;
  }, [isVideoPreview, videoMuted, videoVolume]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      const isCurrentVideoFullscreen = document.fullscreenElement === videoStageRef.current;
      setIsVideoFullscreen(isCurrentVideoFullscreen);
      if (!isCurrentVideoFullscreen) {
        releaseVideoOrientationLock();
      }
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, [releaseVideoOrientationLock]);

  // --- Wheel to Zoom ---
  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay || !activePreview || isVideoPreview) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault(); // Prevent page scroll
      
      const isTrackpadPinch = e.ctrlKey;
      const delta = e.deltaY;
      
      // Much softer, more elegant zoom sensitivity
      const zoomSensitivity = isTrackpadPinch ? 0.005 : 0.0015;

      setTransform((prev) => {
        // 计算阻尼：如果当前处于 <1 的状态，或者是正要缩小到 <1 区域，施加极强的弹性阻力拉拽感
        // 这样基于 delta 的惩罚能绝对防止状态在放大缩小间来回数学震荡，实现完美的跟手感
        const isShrinkingBelowOne = prev.scale < 1 || (prev.scale === 1 && delta > 0);
        const penalty = isShrinkingBelowOne ? 0.15 : 1;
        
        // 基于受到惩罚的滚动量，计算当前应当缩放倍数
        const scaleMultiplier = Math.exp(-delta * zoomSensitivity * penalty);
        
        let newScale = prev.scale * scaleMultiplier;
        
        // 绝对底线和上限保护，防止被过度无限缩小或放大
        // 不要让它缩小到 0.85 以下，否则缩小太多回弹的时候太突兀
        newScale = Math.min(Math.max(newScale, 0.85), 8);
        
        const actualRatio = newScale / prev.scale;
        
        // Let cursor be the zoom origin 
        // We calculate point of cursor relative to screen center
        const cx = e.clientX - window.innerWidth / 2;
        const cy = e.clientY - window.innerHeight / 2;

        const dx = cx - prev.x;
        const dy = cy - prev.y;

        return {
          scale: newScale,
          x: prev.x - dx * (actualRatio - 1),
          y: prev.y - dy * (actualRatio - 1)
        };
      });

      // Debounce snap-back for rubber banding to 1
      if (wheelTimeout.current) clearTimeout(wheelTimeout.current);
      wheelTimeout.current = setTimeout(() => {
        setTransform((prev) => {
          // If the user scaled it smaller than 1, let's gracefully bounce it back
          if (prev.scale < 1) {
            return { scale: 1, x: 0, y: 0 };
          }
          // If the user panned the image while zoomed out, don't snap the pan!
          return prev;
        });
      }, 250); // increased debounce to outlast trackpad momentum
    };

    overlay.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      overlay.removeEventListener('wheel', handleWheel);
      if (wheelTimeout.current) clearTimeout(wheelTimeout.current);
    };
  }, [activePreview, isVideoPreview]);

  const clearVideoControlsHideTimer = useCallback(() => {
    if (videoControlsHideTimer.current) {
      window.clearTimeout(videoControlsHideTimer.current);
      videoControlsHideTimer.current = null;
    }
  }, []);

  const revealVideoControls = useCallback(() => {
    setVideoControlsVisible(true);
    clearVideoControlsHideTimer();

    if (isVideoPreview && isVideoPlaying && !videoError && !isVideoScrubbing) {
      videoControlsHideTimer.current = window.setTimeout(() => {
        setVideoControlsVisible(false);
        videoControlsHideTimer.current = null;
      }, VIDEO_CONTROLS_HIDE_DELAY_MS);
    }
  }, [clearVideoControlsHideTimer, isVideoPlaying, isVideoPreview, isVideoScrubbing, videoError]);

  const toggleVideoControls = useCallback(() => {
    if (!isVideoPreview || videoError || isVideoScrubbing) {
      return;
    }

    if (videoControlsVisible) {
      clearVideoControlsHideTimer();
      setVideoControlsVisible(false);
      return;
    }

    revealVideoControls();
  }, [
    clearVideoControlsHideTimer,
    isVideoPreview,
    isVideoScrubbing,
    revealVideoControls,
    videoControlsVisible,
    videoError,
  ]);

  useEffect(() => {
    clearVideoControlsHideTimer();

    if (!activePreview || !isVideoPreview || !isVideoPlaying || videoError || isVideoScrubbing) {
      setVideoControlsVisible(true);
      return;
    }

    videoControlsHideTimer.current = window.setTimeout(() => {
      setVideoControlsVisible(false);
      videoControlsHideTimer.current = null;
    }, VIDEO_CONTROLS_HIDE_DELAY_MS);

    return clearVideoControlsHideTimer;
  }, [
    activePreview,
    clearVideoControlsHideTimer,
    isVideoPlaying,
    isVideoPreview,
    isVideoScrubbing,
    videoError,
  ]);

  // --- Touch (Pinch & Pan) ---
  const getDistance = (touches: React.TouchList) => {
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  };

  const handleTouchStart = (e: React.TouchEvent) => {
    if (isVideoPreview) {
      return;
    }
    isMoved.current = false;
    if (e.touches.length === 2) {
      setIsPinching(true);
      startPos.current.dist = getDistance(e.touches);
      startPos.current.scale = scale;
    } else if (e.touches.length === 1 && scale > 1) {
      setIsDragging(true);
      startPos.current.x = e.touches[0].clientX;
      startPos.current.y = e.touches[0].clientY;
      startPos.current.posX = x;
      startPos.current.posY = y;
    }
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (isVideoPreview) {
      return;
    }
    if (isPinching && e.touches.length === 2) {
      isMoved.current = true;
      const dist = getDistance(e.touches);
      let newScale = startPos.current.scale * (dist / startPos.current.dist);
      
      // 添加在触摸状态下的极强阻力
      if (newScale < 1) {
        // 如果想猛缩，也只微微缩小
        newScale = 1 - (1 - newScale) * 0.15;
        // 刚性底线，防止回弹感觉太长
        newScale = Math.max(newScale, 0.85);
      } else {
        newScale = Math.min(newScale, 8);
      }

      setTransform(prev => ({
        ...prev,
        scale: newScale
      }));
    } else if (isDragging && e.touches.length === 1) {
      isMoved.current = true;
      const dx = e.touches[0].clientX - startPos.current.x;
      const dy = e.touches[0].clientY - startPos.current.y;
      setTransform(prev => ({
        ...prev,
        x: startPos.current.posX + dx,
        y: startPos.current.posY + dy
      }));
    }
  };

  const handleTouchEnd = () => {
    if (isVideoPreview) {
      return;
    }
    setTimeout(() => {
      isMoved.current = false;
    }, 50);
    setIsPinching(false);
    setIsDragging(false);
    if (scale < 1) {
      setTransform({ scale: 1, x: 0, y: 0 });
    }
  };

  // --- Mouse (Pan) ---
  const handleMouseDown = (e: React.MouseEvent) => {
    if (isVideoPreview) {
      return;
    }
    isMoved.current = false;
    if (scale > 1 && e.button === 0) { // Only left click for dragging
      setIsDragging(true);
      startPos.current.x = e.clientX;
      startPos.current.y = e.clientY;
      startPos.current.posX = x;
      startPos.current.posY = y;
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isVideoPreview) {
      return;
    }
    if (isDragging && scale > 1) {
      isMoved.current = true;
      const dx = e.clientX - startPos.current.x;
      const dy = e.clientY - startPos.current.y;
      setTransform(prev => ({
        ...prev,
        x: startPos.current.posX + dx,
        y: startPos.current.posY + dy
      }));
    }
  };

  const handleMouseUp = () => {
    if (isVideoPreview) {
      return;
    }
    // delay reset slightly to let onClick fire and see isMoved
    setTimeout(() => {
      isMoved.current = false;
    }, 50);
    setIsDragging(false);
  };

  const handleDoubleClick = () => {
    if (isVideoPreview) {
      return;
    }
    if (scale > 1) {
      setTransform({ scale: 1, x: 0, y: 0 });
    } else {
      setTransform({ scale: 2.5, x: 0, y: 0 });
    }
  };

  const handleVideoTogglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video || videoError) {
      return;
    }

    if (video.paused) {
      void video.play().catch(() => setVideoError(true));
    } else {
      video.pause();
    }
  }, [videoError]);

  const handleVideoSkip = useCallback((seconds: number) => {
    const video = videoRef.current;
    if (!video || videoError) {
      return;
    }

    const duration = Number.isFinite(video.duration) ? video.duration : videoDuration;
    const nextTime = clampTime(video.currentTime + seconds, duration);
    video.currentTime = nextTime;
    setVideoCurrentTime(nextTime);
    revealVideoControls();
  }, [revealVideoControls, videoDuration, videoError]);

  const handleVideoVolumeStep = useCallback((delta: number) => {
    const video = videoRef.current;
    const currentVolume = video
      ? (video.muted ? 0 : video.volume)
      : (videoMuted ? 0 : videoVolume);
    const nextVolume = clampVolume(currentVolume + delta);
    setVideoVolume(nextVolume);
    setVideoMuted(nextVolume === 0);
    revealVideoControls();
  }, [revealVideoControls, videoMuted, videoVolume]);

  const isCurrentVideoLandscape = useCallback(() => {
    const video = videoRef.current;
    if (video?.videoWidth && video.videoHeight) {
      return video.videoWidth > video.videoHeight;
    }

    if (previewPhoto?.width && previewPhoto.height) {
      return previewPhoto.width > previewPhoto.height;
    }

    return isLandscapeVideo;
  }, [isLandscapeVideo, previewPhoto?.height, previewPhoto?.width]);

  const handleVideoFullscreen = useCallback(async () => {
    const target = videoStageRef.current;
    if (!target) {
      return;
    }

    if (document.fullscreenElement === target) {
      releaseVideoOrientationLock();
      await document.exitFullscreen().catch(() => undefined);
      return;
    }

    try {
      await target.requestFullscreen?.();
    } catch {
      return;
    }

    if (isCurrentVideoLandscape()) {
      videoOrientationLocked.current = await lockScreenLandscape();
    }
  }, [isCurrentVideoLandscape, releaseVideoOrientationLock]);

  useEffect(() => {
    if (!activePreview || !isVideoPreview || videoError) {
      return;
    }

    const handleVideoKeyDown = (event: KeyboardEvent) => {
      if (isKeyboardEventFromFormControl(event)) {
        return;
      }

      if (event.key === ' ' || event.key === 'Spacebar') {
        event.preventDefault();
        handleVideoTogglePlay();
        revealVideoControls();
        return;
      }

      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        const direction = event.key === 'ArrowLeft' ? -1 : 1;
        const seconds = event.shiftKey ? VIDEO_KEYBOARD_FAST_SEEK_SECONDS : VIDEO_KEYBOARD_SEEK_SECONDS;
        handleVideoSkip(direction * seconds);
        return;
      }

      if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
        event.preventDefault();
        handleVideoVolumeStep(event.key === 'ArrowUp'
          ? VIDEO_KEYBOARD_VOLUME_STEP
          : -VIDEO_KEYBOARD_VOLUME_STEP);
        return;
      }

      if (event.key.toLowerCase() === 'f' && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        void handleVideoFullscreen();
        revealVideoControls();
      }
    };

    window.addEventListener('keydown', handleVideoKeyDown);
    return () => window.removeEventListener('keydown', handleVideoKeyDown);
  }, [
    activePreview,
    handleVideoFullscreen,
    handleVideoSkip,
    handleVideoTogglePlay,
    handleVideoVolumeStep,
    isVideoPreview,
    revealVideoControls,
    videoError,
  ]);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    setChromeSafeImage(null);
    if (!rawImageUrl || !shouldUseSafePhotoPreview) {
      return undefined;
    }

    void createChromeSafePhotoPreviewUrl(rawImageUrl)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }

        objectUrl = url;
        setChromeSafeImage({ sourceUrl: rawImageUrl, objectUrl: url });
      })
      .catch((error: unknown) => {
        console.warn('Chrome-safe photo preview failed:', error);
        if (!cancelled) {
          setIsLoaded(true);
          setImageError(true);
        }
      });

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [rawImageUrl, shouldUseSafePhotoPreview]);

  if (!activePreview) return null;

  const handleOverlayClick = () => {
    // If user was dragging, don't close
    if (isMoved.current) {
      return;
    }
    handleClose();
  };

  const handleDownload = async () => {
    if (isDownloading) return;
    
    try {
      setIsDownloading(true);
      // Fetch the blob directly to bypass browser's default exact view behavior
      const downloadUrl = previewPhoto
        ? previewPhoto.download_url
        : sourceVideoUrl
          ? `${sourceVideoUrl}?download=1`
          : `/api/original/${encodeURIComponent(previewImage?.id ?? '')}?download=1`;
      const response = await fetch(downloadUrl, { credentials: 'same-origin' });
      if (!response.ok) throw new Error('Download failed');
      
      const blob = await response.blob();
      const headerFilename = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1];
      const filename = previewPhoto?.name ?? previewImage?.source_name ?? headerFilename ?? `${activePreview.id}.jpg`;
      
      // Create temporary link and click it
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      
      // Cleanup
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Download error:', err);
      // Fallback
      const fallbackUrl = previewPhoto
        ? previewPhoto.download_url
        : sourceVideoUrl
          ? `${sourceVideoUrl}?download=1`
          : `/api/original/${encodeURIComponent(previewImage?.id ?? '')}?download=1`;
      window.open(fallbackUrl, '_blank');
    } finally {
      setIsDownloading(false);
    }
  };

  const handleConvertPhoto = async () => {
    if (!previewPhoto || previewPhoto.media_type !== 'image' || isConverting) {
      return;
    }

    try {
      setIsConverting(true);
      setNotice({ tone: 'success', message: t('photoConvertPreparing') });
      const result = await convertPhotosToModels([previewPhoto.id]);
      if (result.tasks?.length) {
        upsertTasks(result.tasks);
      }
      setNotice({
        tone: 'success',
        message: t('photoConvertQueued', { count: result.tasks?.length ?? 0 }),
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : t('photoConvertFailed');
      setNotice({ tone: 'error', message });
    } finally {
      setIsConverting(false);
    }
  };

  const handleReconstructVideo = () => {
    if (!previewPhoto || previewPhoto.media_type !== 'video') {
      return;
    }
    const targetVideo = previewPhoto;
    videoRef.current?.pause();
    releaseVideoOrientationLock();
    if (document.fullscreenElement === videoStageRef.current) {
      void document.exitFullscreen().catch(() => undefined);
    }
    setPreviewPhoto(null);
    openVideoReconstructionDialog(targetVideo);
  };

  const handleNavigatePhoto = (direction: -1 | 1) => {
    if (!previewPhoto || photoItems.length === 0) {
      return;
    }

    const index = photoItems.findIndex((photo) => photo.id === previewPhoto.id);
    if (index < 0) {
      return;
    }

    const next = photoItems[index + direction];
    if (next) {
      setPreviewPhoto(next);
    }
  };

  const handleVideoTimeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const video = videoRef.current;
    if (!video || !videoDuration) {
      return;
    }

    const nextTime = Number(event.target.value);
    video.currentTime = nextTime;
    setVideoCurrentTime(nextTime);
    revealVideoControls();
  };

  const handleVideoVolumeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextVolume = Number(event.target.value);
    setVideoVolume(nextVolume);
    setVideoMuted(nextVolume === 0);
    revealVideoControls();
  };

  const handleVideoMuteToggle = () => {
    setVideoMuted((current) => !current);
    revealVideoControls();
  };

  const clearVideoLongPressTimer = () => {
    if (videoLongPressTimer.current) {
      window.clearTimeout(videoLongPressTimer.current);
      videoLongPressTimer.current = null;
    }
  };

  const handleVideoPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isVideoPreview || event.pointerType === 'mouse' || videoError) {
      return;
    }

    const target = event.target as HTMLElement;
    if (target.closest('button,input')) {
      return;
    }

    const video = videoRef.current;
    if (!video || !Number.isFinite(video.duration) || video.duration <= 0) {
      return;
    }

    event.currentTarget.setPointerCapture(event.pointerId);
    clearVideoLongPressTimer();
    videoScrubRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      baseTime: video.currentTime,
      targetTime: video.currentTime,
      wasPlaying: !video.paused,
      isTouchLike: true,
      activated: false,
      cancelled: false,
    };
    videoLongPressTimer.current = window.setTimeout(() => {
      const current = videoScrubRef.current;
      if (!current || !current.isTouchLike) {
        return;
      }
      current.activated = true;
      current.wasPlaying = !video.paused;
      video.pause();
      setIsVideoScrubbing(true);
      setVideoScrubLabel(formatVideoScrubLabel(0, current.baseTime));
    }, VIDEO_LONG_PRESS_MS);
  };

  const handleVideoPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (isVideoPreview && !videoError && event.pointerType === 'mouse') {
      revealVideoControls();
    }

    const current = videoScrubRef.current;
    const video = videoRef.current;
    if (!current || !video || !current.isTouchLike) {
      return;
    }

    const deltaX = event.clientX - current.startX;
    const deltaY = event.clientY - current.startY;
    if (!current.activated && Math.hypot(deltaX, deltaY) > VIDEO_SCRUB_THRESHOLD_PX) {
      clearVideoLongPressTimer();
      current.cancelled = true;
    }
    if (!current.activated) {
      return;
    }

    event.preventDefault();
    const offsetSeconds = deltaX * VIDEO_FINE_SCRUB_SECONDS_PER_PX;
    const duration = Number.isFinite(video.duration) ? video.duration : videoDuration;
    const targetTime = clampTime(current.baseTime + offsetSeconds, duration);
    current.targetTime = targetTime;
    setVideoCurrentTime(targetTime);
    setVideoScrubLabel(formatVideoScrubLabel(offsetSeconds, targetTime));
  };

  const handleVideoPointerUp = (event: React.PointerEvent<HTMLDivElement>, isCancelled = false) => {
    const target = event.target as HTMLElement;
    if (target.closest('button,input')) {
      return;
    }

    const current = videoScrubRef.current;
    const video = videoRef.current;
    clearVideoLongPressTimer();
    videoScrubRef.current = null;

    if (!current || !video) {
      if (!isCancelled) {
        toggleVideoControls();
      }
      return;
    }

    if (isCancelled || current.cancelled) {
      // A short move before long-press should be treated as neither tap nor scrub.
    } else if (current.activated) {
      video.currentTime = current.targetTime;
      setVideoCurrentTime(current.targetTime);
      if (current.wasPlaying) {
        void video.play().catch(() => setVideoError(true));
      }
      revealVideoControls();
    } else {
      toggleVideoControls();
    }

    setIsVideoScrubbing(false);
    setVideoScrubLabel(null);
  };

  // Prevent clicks inside the container from closing the viewer
  const handleContainerClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  // The actual high quality image URL, or an Android Chrome SDR-safe Blob URL.
  const chromeSafeImageUrl = chromeSafeImage?.sourceUrl === rawImageUrl
    ? chromeSafeImage.objectUrl
    : null;
  const imageUrl = shouldUseSafePhotoPreview ? chromeSafeImageUrl : rawImageUrl;
  const isWaitingForSafeImage = shouldUseSafePhotoPreview && !chromeSafeImageUrl && !imageError;
  const videoUrl = isVideoPreview
    ? previewPhoto?.playback_url ?? previewPhoto?.preview_url ?? sourceVideoUrl
    : null;
  const photoIndex = previewPhoto
    ? photoItems.findIndex((photo) => photo.id === previewPhoto.id)
    : -1;
  const hasPreviousPhoto = photoIndex > 0;
  const hasNextPhoto = previewPhoto ? photoIndex >= 0 && photoIndex < photoItems.length - 1 : false;
  const videoProgress = videoDuration > 0 ? `${(videoCurrentTime / videoDuration) * 100}%` : '0%';
  const volumeProgress = `${(videoMuted ? 0 : videoVolume) * 100}%`;
  const videoControlsHidden = !videoControlsVisible && !isVideoScrubbing && !videoError;
  const mediaMeta = previewPhoto
    ? getPreviewMetaLabel(previewPhoto, t('unknownSize'))
    : isSourceVideoPreview
      ? t('photoVideo')
    : null;
  const videoAspectRatio = isVideoPreview
    ? getVideoAspectRatio(previewPhoto, videoNaturalSize)
    : VIDEO_FALLBACK_ASPECT_RATIO;
  const videoViewerWidthVh = Math.min(168, Math.max(40, videoAspectRatio * VIDEO_VIEWER_HEIGHT_VH));
  const videoViewerStyle = {
    '--video-aspect-ratio': String(videoAspectRatio),
    '--video-viewer-width': `min(calc(100vw - 96px), ${videoViewerWidthVh.toFixed(3)}vh)`,
  } as React.CSSProperties;

  const isAnimating = (!isDragging && !isPinching);
  const wrapperStyle: React.CSSProperties = {
    transform: `translate3d(${x}px, ${y}px, 0) scale(${scale})`,
    transition: isAnimating ? 'transform 0.4s cubic-bezier(0.16, 1, 0.3, 1)' : 'none',
    cursor: scale > 1 ? (isDragging ? 'grabbing' : 'grab') : 'auto',
    willChange: 'transform'
  };

  return (
    <div 
      className={`${styles.overlay} ${isClosing ? styles.closing : ''}`}
      onClick={handleOverlayClick}
      ref={overlayRef}
      tabIndex={-1}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onDoubleClick={handleDoubleClick}
    >
      <div className={styles.controls} onClick={(e) => { e.stopPropagation(); setIsDragging(false); }}>
        {previewPhoto && previewPhoto.media_type === 'image' ? (
          <button
            className={`${styles.controlBtn} ${isConverting ? styles.downloading : ''}`}
            onClick={handleConvertPhoto}
            data-tooltip={t('photoConvertOne')}
            disabled={isConverting}
            type="button"
          >
            <SparklesIcon width={20} height={20} />
          </button>
        ) : null}
        {previewPhoto && previewPhoto.media_type === 'video' ? (
          <button
            className={styles.controlBtn}
            onClick={handleReconstructVideo}
            data-tooltip={t('videoReconGenerate3d')}
            type="button"
          >
            <SparklesIcon width={20} height={20} />
          </button>
        ) : null}
        <button 
          className={`${styles.controlBtn} ${isDownloading ? styles.downloading : ''}`} 
          onClick={handleDownload}
          data-tooltip={previewPhoto ? t('photoDownload') : t('download')}
          disabled={isDownloading}
          type="button"
        >
          <DownloadIcon width={20} height={20} />
        </button>
        <button 
          className={styles.controlBtn} 
          onClick={handleClose}
          data-tooltip={t('cancel') || 'Close'}
          type="button"
        >
          <CloseIcon width={20} height={20} />
        </button>
      </div>

      {previewPhoto ? (
        <>
          <button
            className={[styles.navBtn, styles.navPrev].join(' ')}
            onClick={(event) => { event.stopPropagation(); handleNavigatePhoto(-1); }}
            disabled={!hasPreviousPhoto}
            aria-label={t('photoPrevious')}
            type="button"
          >
            <ChevronLeftIcon width={24} height={24} />
          </button>
          <button
            className={[styles.navBtn, styles.navNext].join(' ')}
            onClick={(event) => { event.stopPropagation(); handleNavigatePhoto(1); }}
            disabled={!hasNextPhoto}
            aria-label={t('photoNext')}
            type="button"
          >
            <ChevronRightIcon width={24} height={24} />
          </button>
        </>
      ) : null}

      <div 
        className={[styles.container, isVideoPreview ? styles.videoContainer : ''].filter(Boolean).join(' ')}
        onClick={handleContainerClick}
        style={isVideoPreview ? videoViewerStyle : wrapperStyle}
      >
        {isVideoPreview && videoUrl ? (
          <div
            ref={videoStageRef}
            className={styles.videoStage}
            onPointerDown={handleVideoPointerDown}
            onPointerMove={handleVideoPointerMove}
            onPointerUp={(event) => handleVideoPointerUp(event)}
            onPointerCancel={(event) => handleVideoPointerUp(event, true)}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
            }}
          >
            {!isLoaded && !videoError ? <div className={styles.loadingSpinner} /> : null}
            <video
              ref={videoRef}
              className={[styles.video, isLoaded ? styles.loaded : ''].filter(Boolean).join(' ')}
              src={videoUrl}
              poster={previewPhoto?.poster_url ?? previewImage?.thumb_url ?? undefined}
              preload="metadata"
              {...VIDEO_INLINE_PLAYBACK_ATTRIBUTES}
              onLoadedMetadata={(event) => {
                const video = event.currentTarget;
                setIsLoaded(true);
                setVideoError(false);
                setVideoDuration(Number.isFinite(video.duration) ? video.duration : 0);
                setVideoCurrentTime(video.currentTime);
                setIsLandscapeVideo(video.videoWidth > video.videoHeight);
                setVideoNaturalSize(video.videoWidth && video.videoHeight
                  ? { width: video.videoWidth, height: video.videoHeight }
                  : null);
              }}
              onTimeUpdate={(event) => setVideoCurrentTime(event.currentTarget.currentTime)}
              onPlay={() => setIsVideoPlaying(true)}
              onPause={() => setIsVideoPlaying(false)}
              onVolumeChange={(event) => {
                setVideoVolume(event.currentTarget.volume);
                setVideoMuted(event.currentTarget.muted);
              }}
              onError={() => {
                setIsLoaded(true);
                setVideoError(true);
                setIsVideoPlaying(false);
              }}
            >
              <source src={videoUrl} type={previewPhoto?.mime_type ?? undefined} />
            </video>

            {videoError ? (
              <div className={styles.videoError}>
                <div className={styles.videoErrorCard}>
                  <div className={styles.videoErrorIcon}>
                    <PlayIcon width={22} height={22} />
                  </div>
                  <strong>{t('photoVideoPlaybackFailedTitle')}</strong>
                  <span>{t('photoVideoPlaybackFailedHint')}</span>
                  <button
                    className={styles.videoErrorAction}
                    onClick={handleDownload}
                    type="button"
                  >
                    <DownloadIcon width={16} height={16} />
                    {t('photoDownloadVideo')}
                  </button>
                </div>
              </div>
            ) : null}

            {isVideoScrubbing && videoScrubLabel ? (
              <div className={styles.scrubBubble}>{videoScrubLabel}</div>
            ) : null}

            <button
              className={[
                styles.videoCenterPlay,
                isVideoPlaying || videoError ? styles.videoCenterPlayHidden : '',
              ].filter(Boolean).join(' ')}
              onClick={(event) => {
                event.stopPropagation();
                handleVideoTogglePlay();
              }}
              onPointerDown={(event) => event.stopPropagation()}
              onPointerUp={(event) => event.stopPropagation()}
              type="button"
              aria-label={t('photoVideoPlay')}
            >
              <PlayIcon width={28} height={28} />
            </button>

            <div
              className={[
                styles.videoControls,
                videoControlsHidden ? styles.videoControlsHidden : '',
              ].filter(Boolean).join(' ')}
              onClick={(event) => event.stopPropagation()}
              onPointerDown={(event) => {
                event.stopPropagation();
                revealVideoControls();
              }}
              onPointerMove={() => revealVideoControls()}
              onPointerUp={(event) => event.stopPropagation()}
              onFocus={() => revealVideoControls()}
            >
              <div className={styles.videoTimeline}>
                <input
                  className={styles.videoRange}
                  style={{ '--video-progress': videoProgress } as React.CSSProperties}
                  type="range"
                  min="0"
                  max={videoDuration || 0}
                  step="0.05"
                  value={Math.min(videoCurrentTime, videoDuration || 0)}
                  disabled={!videoDuration || videoError}
                  aria-label={t('photoVideoSeek')}
                  onChange={handleVideoTimeChange}
                />
                <div className={styles.videoTime}>
                  <span>{formatVideoTime(videoCurrentTime)}</span>
                  <span>{formatVideoTime(videoDuration)}</span>
                </div>
              </div>

              <div className={styles.videoControlRow}>
                <div className={styles.videoVolumeGroup}>
                  <button
                    className={styles.videoControlBtn}
                    onClick={handleVideoMuteToggle}
                    disabled={videoError}
                    type="button"
                    aria-label={videoMuted ? t('photoVideoUnmute') : t('photoVideoMute')}
                    data-tooltip={videoMuted ? t('photoVideoUnmute') : t('photoVideoMute')}
                  >
                    {videoMuted || videoVolume === 0
                      ? <VolumeMutedIcon width={17} height={17} />
                      : <VolumeIcon width={17} height={17} />}
                  </button>

                  <input
                    className={[styles.videoRange, styles.volumeRange].join(' ')}
                    style={{ '--video-progress': volumeProgress } as React.CSSProperties}
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={videoMuted ? 0 : videoVolume}
                    disabled={videoError}
                    aria-label={t('photoVideoVolume')}
                    onChange={handleVideoVolumeChange}
                  />
                </div>

                <div className={styles.videoTransportGroup}>
                  <button
                    className={styles.videoControlBtn}
                    onClick={() => {
                      handleVideoSkip(-15);
                    }}
                    disabled={!videoDuration || videoError}
                    type="button"
                    aria-label={t('photoVideoBack15')}
                    data-tooltip={t('photoVideoBack15')}
                  >
                    <span className={styles.videoSkipLabel}>-15s</span>
                  </button>

                  <button
                    className={styles.videoControlBtn}
                    onClick={() => {
                      handleVideoTogglePlay();
                      revealVideoControls();
                    }}
                    disabled={videoError}
                    type="button"
                    aria-label={isVideoPlaying ? t('photoVideoPause') : t('photoVideoPlay')}
                    data-tooltip={isVideoPlaying ? t('photoVideoPause') : t('photoVideoPlay')}
                  >
                    {isVideoPlaying ? <PauseIcon width={17} height={17} /> : <PlayIcon width={17} height={17} />}
                  </button>

                  <button
                    className={styles.videoControlBtn}
                    onClick={() => {
                      handleVideoSkip(15);
                    }}
                    disabled={!videoDuration || videoError}
                    type="button"
                    aria-label={t('photoVideoForward15')}
                    data-tooltip={t('photoVideoForward15')}
                  >
                    <span className={styles.videoSkipLabel}>+15s</span>
                  </button>
                </div>

                <div className={styles.videoUtilityGroup}>
                  <button
                    className={styles.videoControlBtn}
                    onClick={handleDownload}
                    disabled={isDownloading}
                    type="button"
                    aria-label={t('photoDownloadVideo')}
                    data-tooltip={t('photoDownloadVideo')}
                  >
                    <DownloadIcon width={17} height={17} />
                  </button>

                  <button
                    className={styles.videoControlBtn}
                    onClick={handleVideoFullscreen}
                    disabled={videoError}
                    type="button"
                    aria-label={isVideoFullscreen ? t('photoVideoExitFullscreen') : t('photoVideoFullscreen')}
                    data-tooltip={isVideoFullscreen ? t('photoVideoExitFullscreen') : t('photoVideoFullscreen')}
                  >
                    {isVideoFullscreen
                      ? <ExitFullscreenIcon width={17} height={17} />
                      : <FullscreenIcon width={17} height={17} />}
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className={styles.imageWrapper}>
            {!isLoaded && <div className={styles.loadingSpinner} />}
            {imageError ? <div className={styles.imageError}>{t('photoOriginalLoadFailed')}</div> : null}
            {imageUrl && !isWaitingForSafeImage ? (
              <img
                src={imageUrl}
                alt={activeName}
                className={`${styles.image} ${isLoaded ? styles.loaded : ''}`}
                onLoad={() => {
                  setIsLoaded(true);
                  setImageError(false);
                }}
                onError={() => {
                  setIsLoaded(true);
                  setImageError(true);
                }}
                draggable={false}
              />
            ) : null}
          </div>
        )}
      </div>

      {notice ? (
        <div
          className={[
            styles.notice,
            notice.tone === 'success' ? styles.noticeSuccess : styles.noticeError,
          ].join(' ')}
          onClick={(event) => event.stopPropagation()}
          role="status"
          aria-live="polite"
        >
          <span>{notice.message}</span>
          <button
            onClick={() => setNotice(null)}
            type="button"
            data-tooltip={t('close')}
            aria-label={t('close')}
          >
            <CloseIcon width={13} height={13} />
          </button>
        </div>
      ) : null}

      {previewPhoto || isSourceVideoPreview ? (
        <div
          className={[
            styles.infoPanel,
            isVideoPreview ? styles.videoInfoPanel : '',
          ].filter(Boolean).join(' ')}
          onClick={(event) => event.stopPropagation()}
        >
          <span className={styles.infoTitle} data-tooltip={activeName}>{activeName}</span>
          <span className={styles.infoMeta}>
            {mediaMeta}
          </span>
        </div>
      ) : null}
    </div>
  );
}

function clampTime(value: number, duration: number): number {
  if (!Number.isFinite(duration) || duration <= 0) {
    return Math.max(0, value);
  }
  return Math.min(duration, Math.max(0, value));
}

function clampVolume(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function isKeyboardEventFromFormControl(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null;
  if (!target) {
    return false;
  }

  const formControl = target.closest('input,textarea,select,[contenteditable="true"]');
  if (!formControl) {
    return false;
  }

  return !(formControl instanceof HTMLInputElement) || formControl.type !== 'button';
}

function formatVideoTime(value: number): string {
  if (!Number.isFinite(value) || value <= 0) {
    return '0:00';
  }

  const totalSeconds = Math.floor(value);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function formatVideoScrubLabel(offsetSeconds: number, targetTime: number): string {
  const sign = offsetSeconds >= 0 ? '+' : '-';
  const offset = Math.abs(offsetSeconds);
  return `${sign}${offset.toFixed(1)}s · ${formatVideoTime(targetTime)}`;
}

function getVideoAspectRatio(
  photo: { width?: number | null; height?: number | null } | null | undefined,
  naturalSize: { width: number; height: number } | null,
): number {
  const width = naturalSize?.width ?? photo?.width;
  const height = naturalSize?.height ?? photo?.height;
  if (!width || !height || width <= 0 || height <= 0) {
    return VIDEO_FALLBACK_ASPECT_RATIO;
  }
  return Math.min(4, Math.max(0.45, width / height));
}

function getPreviewMetaLabel(
  photo: { media_type?: string; width?: number | null; height?: number | null; duration?: number | null; video_codec?: string | null },
  fallback: string,
): string {
  const resolution = photo.width && photo.height ? `${photo.width} × ${photo.height}` : null;
  if (photo.media_type !== 'video') {
    return resolution ?? fallback;
  }

  const duration = typeof photo.duration === 'number' ? formatVideoTime(photo.duration) : null;
  const codec = photo.video_codec ? photo.video_codec.toUpperCase() : null;
  return [resolution, duration, codec].filter(Boolean).join(' · ') || fallback;
}
