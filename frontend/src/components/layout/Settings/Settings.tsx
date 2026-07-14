import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppStore } from '@/store/useAppStore';
import {
    ApiError,
    fetchAuthStatus,
    fetchPhotoGalleryCacheStats,
    fetchSettings,
    fetchVideoReconstructionStatus,
    clearPhotoGalleryCache,
    logoutAccessSession,
    restartServer,
    revokeAccessSessions,
    saveSettings,
    setAccessCode,
    browseFolder,
    convertAllToSpz,
    updateAuthSettings,
} from '@/api';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import type {
    AuthStatusResponse,
    ModelFormat,
    PhotoGalleryCacheStats,
    VideoReconstructionConfig,
    VideoReconstructionDependencies,
    VideoReconstructionEngine,
    VideoReconstructionPresetQuality,
    VideoReconstructionVramBudget,
} from '@/types';
import {
    REVEAL_EFFECT_SETTINGS_OPTIONS,
    type RevealEffectPreferenceId,
} from '@/utils/viewerRevealEffects';
import styles from './Settings.module.css';

// Folder icon
const FolderIcon = () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
    </svg>
);

const DEFAULT_VIDEO_CONFIG: VideoReconstructionConfig = {
    default_quality: 'high',
    default_engine: 'auto',
    vram_budget: '12gb',
    keep_intermediate_files: false,
};

export const Settings: React.FC = () => {
    const { t } = useTranslation();
    const {
        settingsModalOpen,
        setSettingsModalOpen,
        setLoading,
        serverModelFormat,
        setServerModelFormat,
        setLocalModelFormat,
        effectiveModelFormat,
        isLocalAccess,
        viewerDefaultRevealEffect,
        setViewerDefaultRevealEffect,
        quickPresetMode,
        setQuickPresetMode,
        applyQuickPreset,
        isLodEnabled,
        toggleLod,
        lodPreset,
        setLodPreset,
        lodCompareMode,
        setLodCompareMode,
        canCompareLod,
        radModeEnabled,
        setRadModeEnabled,
        radPagedEnabled,
        setRadPagedEnabled,
        xrUpdateMode,
        setXrUpdateMode,
        isHighFidelity,
        toggleHighFidelity,
        currentModelId,
        currentModelUrl,
        currentModelFormat: storeModelFormat,
        currentModelSize,
        setCurrentModel,
        authStatus,
        setAuthStatus,
        setVideoReconstructionStatus,
        openVideoReconstructionGuide,
    } = useAppStore();
    const [workspaceFolder, setWorkspaceFolder] = useState('');
    const [modelFormat, setModelFormat] = useState<ModelFormat>('spz');
    const [defaultRevealEffect, setDefaultRevealEffect] = useState<RevealEffectPreferenceId>(viewerDefaultRevealEffect);
    const [isSaving, setIsSaving] = useState(false);
    const [isConverting, setIsConverting] = useState(false);
    const [accessControlEnabled, setAccessControlEnabled] = useState(false);
    const [savedAccessControlEnabled, setSavedAccessControlEnabled] = useState(false);
    const [accessCode, setAccessCodeValue] = useState('');
    const [sessionDays, setSessionDays] = useState(30);
    const [savedSessionDays, setSavedSessionDays] = useState(30);
    const [allowRemoteGeneration, setAllowRemoteGeneration] = useState(false);
    const [savedAllowRemoteGeneration, setSavedAllowRemoteGeneration] = useState(false);
    const [lanBindEnabled, setLanBindEnabled] = useState(true);
    const [savedLanBindEnabled, setSavedLanBindEnabled] = useState(true);
    const [isAccessSaving, setIsAccessSaving] = useState(false);
    const [isRevokingSessions, setIsRevokingSessions] = useState(false);
    const [isLoggingOut, setIsLoggingOut] = useState(false);
    const [accessMessage, setAccessMessage] = useState<string | null>(null);
    const [photoCacheStats, setPhotoCacheStats] = useState<PhotoGalleryCacheStats | null>(null);
    const [isPhotoCacheLoading, setIsPhotoCacheLoading] = useState(false);
    const [isPhotoCacheClearing, setIsPhotoCacheClearing] = useState(false);
    const [photoCacheMessage, setPhotoCacheMessage] = useState<string | null>(null);
    const [photoCacheConfirmOpen, setPhotoCacheConfirmOpen] = useState(false);
    const [videoConfig, setVideoConfig] = useState<VideoReconstructionConfig>(DEFAULT_VIDEO_CONFIG);
    const [savedVideoConfig, setSavedVideoConfig] = useState<VideoReconstructionConfig>(DEFAULT_VIDEO_CONFIG);
    const [videoDependencies, setVideoDependencies] = useState<VideoReconstructionDependencies | null>(null);
    const [videoStatusLoading, setVideoStatusLoading] = useState(false);
    const [videoMessage, setVideoMessage] = useState<string | null>(null);

    // Track if workspace_folder changed (needs restart)
    const [originalWorkspace, setOriginalWorkspace] = useState('');

    const reloadCurrentModel = () => {
        if (currentModelId && currentModelUrl) {
            const fmt = storeModelFormat;
            setCurrentModel(null, null);
            setTimeout(() => setCurrentModel(currentModelId, currentModelUrl, fmt, currentModelSize), 50);
        }
    };

    const applyManualChange = (action: () => void) => {
        if (quickPresetMode !== 'manual') {
            setQuickPresetMode('manual');
        }
        action();
    };

    const handleQuickPresetChange = (mode: 'performance' | 'balanced' | 'detail' | 'manual') => {
        if (mode === 'manual') {
            setQuickPresetMode('manual');
            return;
        }

        applyQuickPreset(mode);
        reloadCurrentModel();
    };

    const applyAccessStatus = useCallback((status: AuthStatusResponse) => {
        setAuthStatus(status);
        setAccessControlEnabled(status.access_control_enabled);
        setSavedAccessControlEnabled(status.access_control_enabled);
        setSessionDays(status.session_days);
        setSavedSessionDays(status.session_days);
        setAllowRemoteGeneration(status.allow_remote_generation);
        setSavedAllowRemoteGeneration(status.allow_remote_generation);
        setLanBindEnabled(status.lan_bind_enabled);
        setSavedLanBindEnabled(status.lan_bind_enabled);
    }, [setAuthStatus]);

    const loadSettings = useCallback(async () => {
        try {
            const data = await fetchSettings();
            if (data.workspace_folder) {
                setWorkspaceFolder(data.workspace_folder);
                setOriginalWorkspace(data.workspace_folder);
            }
            if (data.video_reconstruction) {
                setVideoConfig(data.video_reconstruction);
                setSavedVideoConfig(data.video_reconstruction);
            }
            const nextAuthStatus = await fetchAuthStatus();
            applyAccessStatus(nextAuthStatus);
            // We do not overwrite modelFormat here because effectiveModelFormat() 
            // already handles client-side overrides.
        } catch (error) {
            console.error('Failed to load settings:', error);
        }
    }, [applyAccessStatus]);

    const loadPhotoCacheStats = useCallback(async () => {
        if (!isLocalAccess) return;
        setIsPhotoCacheLoading(true);
        try {
            const stats = await fetchPhotoGalleryCacheStats();
            setPhotoCacheStats(stats);
            setPhotoCacheMessage(null);
        } catch (error) {
            const message = error instanceof Error ? error.message : t('photoCacheLoadFailed');
            setPhotoCacheMessage(message);
        } finally {
            setIsPhotoCacheLoading(false);
        }
    }, [isLocalAccess, t]);

    const loadVideoReconstructionStatus = useCallback(async (forceRefresh = false) => {
        setVideoStatusLoading(true);
        try {
            const status = await fetchVideoReconstructionStatus({ refresh: forceRefresh });
            setVideoConfig(status.config);
            setSavedVideoConfig(status.config);
            setVideoDependencies(status.dependencies);
            setVideoReconstructionStatus(status.dependencies, status.config);
            setVideoMessage(null);
        } catch (error) {
            const message = error instanceof Error ? error.message : t('videoReconStatusLoadFailed');
            setVideoMessage(message);
        } finally {
            setVideoStatusLoading(false);
        }
    }, [setVideoReconstructionStatus, t]);

    // Load settings when modal opens
    useEffect(() => {
        if (settingsModalOpen) {
            setModelFormat(effectiveModelFormat());
            setDefaultRevealEffect(viewerDefaultRevealEffect);
            setAccessMessage(null);
            loadSettings();
            void loadPhotoCacheStats();
            void loadVideoReconstructionStatus();
        }
    }, [
        settingsModalOpen,
        effectiveModelFormat,
        viewerDefaultRevealEffect,
        loadSettings,
        loadPhotoCacheStats,
        loadVideoReconstructionStatus,
    ]);

    const handleClose = () => {
        setSettingsModalOpen(false);
    };

    const handleBackdropClick = (e: React.MouseEvent) => {
        if (e.target === e.currentTarget) {
            handleClose();
        }
    };

    const handleBrowse = async () => {
        try {
            const result = await browseFolder('Select Workspace Folder', workspaceFolder);
            if (result.path) {
                setWorkspaceFolder(result.path);
            }
        } catch (error) {
            console.error('Browse failed:', error);
        }
    };

    const handleSave = async () => {
        setIsSaving(true);
        try {
            if (defaultRevealEffect !== viewerDefaultRevealEffect) {
                setViewerDefaultRevealEffect(defaultRevealEffect);
            }

            // For non-local users, simply save format preference to localStorage and close.
            if (!isLocalAccess) {
                setLocalModelFormat(modelFormat);
                handleClose();
                return;
            }

            const payload: {
                model_format?: ModelFormat;
                workspace_folder?: string;
                video_reconstruction?: VideoReconstructionConfig;
            } = {};

            // Always save model_format
            if (modelFormat !== serverModelFormat) {
                payload.model_format = modelFormat;
            }

            // Only include workspace if changed
            const workspaceChanged = workspaceFolder !== originalWorkspace;
            if (workspaceChanged) {
                payload.workspace_folder = workspaceFolder;
            }

            if (isLocalAccess && hasVideoSettingsChanges) {
                payload.video_reconstruction = videoConfig;
            }

            // 切换局域网监听绑定需要重启服务才能生效（与工作目录一致的体验）
            const bindChanged = lanBindEnabled !== savedLanBindEnabled;

            // 没有任何变更直接关闭
            if (Object.keys(payload).length === 0 && !hasAccessSettingsChanges) {
                handleClose();
                return;
            }

            // 先持久化门禁相关设置（启用状态、会话天数、远程生成、局域网绑定）
            if (hasAccessSettingsChanges) {
                const status = await updateAuthSettings({
                    enabled: accessControlEnabled,
                    session_days: sessionDays,
                    allow_remote_generation: accessControlEnabled ? allowRemoteGeneration : false,
                    lan_bind_enabled: lanBindEnabled,
                });
                applyAccessStatus(status);
            }

            // 再保存通用设置（模型格式、工作目录）
            let needsServerRestart = bindChanged;
            if (Object.keys(payload).length > 0) {
                const result = await saveSettings(payload);
                if (!result.success) {
                    alert('Error: ' + (result.error || 'Unknown error'));
                    return;
                }
                if (payload.model_format) {
                    setServerModelFormat(modelFormat);
                    setLocalModelFormat(null);
                }
                if (payload.video_reconstruction) {
                    setSavedVideoConfig(payload.video_reconstruction);
                    setVideoMessage(t('videoReconSettingsSaved'));
                }
                needsServerRestart = needsServerRestart || Boolean(result.needs_restart);
            }

            // 工作目录或局域网绑定变更都需要重启服务，统一自动重启
            if (needsServerRestart) {
                handleClose();
                setLoading(true, t('lanBindRestarting'));
                try {
                    await restartServer();
                } catch {
                    // 重启会断开连接，属预期行为
                }
                setTimeout(() => {
                    window.location.reload();
                }, 3000);
            } else {
                handleClose();
            }
        } catch (error) {
            console.error('Failed to save settings:', error);
            alert('Failed to save settings');
        } finally {
            setIsSaving(false);
        }
    };

    const handleConvertAll = async () => {
        setIsConverting(true);
        try {
            const result = await convertAllToSpz();
            if (result.success) {
                const msg = t('convertAllResult', {
                    converted: result.converted,
                    skipped: result.skipped,
                    failed: result.failed,
                    total: result.total
                });
                alert(msg);
            }
        } catch (error) {
            console.error('Batch conversion failed:', error);
            alert('Batch conversion failed');
        } finally {
            setIsConverting(false);
        }
    };

    const handleClearPhotoCache = async () => {
        if (!isLocalAccess || isPhotoCacheClearing) return;
        setIsPhotoCacheClearing(true);
        setPhotoCacheMessage(null);
        try {
            const result = await clearPhotoGalleryCache('generated');
            setPhotoCacheStats(result.stats);
            setPhotoCacheMessage(t('photoCacheClearComplete', {
                files: result.removed.files,
                size: formatCacheSize(result.removed.bytes),
            }));
            setPhotoCacheConfirmOpen(false);
        } catch (error) {
            const message = error instanceof ApiError && error.status === 403
                ? t('ownerOnlyAction')
                : error instanceof Error
                    ? error.message
                    : t('photoCacheClearFailed');
            setPhotoCacheMessage(message);
        } finally {
            setIsPhotoCacheClearing(false);
        }
    };

    const updateVideoConfig = (patch: Partial<VideoReconstructionConfig>) => {
        setVideoConfig((current) => ({ ...current, ...patch }));
    };

    const renderDependencyGroup = (
        groupKey: 'required' | 'stable',
        group?: VideoReconstructionDependencies['required'],
    ) => {
        const checking = Boolean(videoDependencies?.summary.checking && !group?.tools.length);
        const available = Boolean(group?.available);
        const dependencyMessage = checking
            ? t('videoReconCheckingDependencies')
            : group?.message || t(`videoReconDependencyHint.${groupKey}`);
        return (
            <div className={styles.dependencyRow}>
                <div>
                    <span className={styles.dependencyTitle}>{t(`videoReconDependency.${groupKey}`)}</span>
                    <p>{dependencyMessage}</p>
                </div>
                <span className={`${styles.statusPill} ${available ? styles.statusOk : styles.statusWarn}`}>
                    {checking
                        ? t('videoReconDependencyChecking')
                        : available
                            ? t('videoReconDependencyAvailable')
                            : t('videoReconDependencyMissing')}
                </span>
            </div>
        );
    };

    const getAccessErrorMessage = (error: unknown) => {
        if (error instanceof ApiError) {
            if (error.status === 403) {
                return t('ownerOnlyAction');
            }
            if (error.data?.code === 'ACCESS_CODE_TOO_SHORT') {
                return t('accessCodeTooShort');
            }
            return error.message;
        }
        return t('accessControlSaveFailed');
    };

    const hasAccessSettingsChanges =
        accessControlEnabled !== savedAccessControlEnabled ||
        sessionDays !== savedSessionDays ||
        allowRemoteGeneration !== savedAllowRemoteGeneration ||
        lanBindEnabled !== savedLanBindEnabled;
    const hasVideoSettingsChanges =
        videoConfig.default_quality !== savedVideoConfig.default_quality ||
        videoConfig.default_engine !== savedVideoConfig.default_engine ||
        videoConfig.vram_budget !== savedVideoConfig.vram_budget ||
        videoConfig.keep_intermediate_files !== savedVideoConfig.keep_intermediate_files;

    const accessSettingsStateText = (() => {
        if (hasAccessSettingsChanges) {
            return t('accessSettingsUnsaved');
        }
        if (!accessControlEnabled) {
            return t('accessControlSavedOff');
        }
        return t(allowRemoteGeneration ? 'remoteGenerationSavedOn' : 'remoteGenerationSavedOff');
    })();

    const handleAccessControlToggle = (enabled: boolean) => {
        setAccessControlEnabled(enabled);
        if (!enabled) {
            setAllowRemoteGeneration(false);
        }
    };

    const handleSaveAccessCode = async () => {
        if (!isLocalAccess) return;
        setIsAccessSaving(true);
        setAccessMessage(null);
        try {
            const status = await setAccessCode({
                password: accessCode,
                enabled: true,
                session_days: sessionDays,
                allow_remote_generation: allowRemoteGeneration,
            });
            applyAccessStatus(status);
            setAccessCodeValue('');
            setAccessMessage(t('accessCodeSaved'));
        } catch (error) {
            setAccessMessage(getAccessErrorMessage(error));
        } finally {
            setIsAccessSaving(false);
        }
    };

    const handleRevokeSessions = async () => {
        if (!isLocalAccess) return;
        setIsRevokingSessions(true);
        setAccessMessage(null);
        try {
            const status = await revokeAccessSessions();
            setAuthStatus(status);
            setAccessMessage(t('accessSessionsRevoked'));
        } catch (error) {
            setAccessMessage(getAccessErrorMessage(error));
        } finally {
            setIsRevokingSessions(false);
        }
    };

    const handleLogout = async () => {
        setIsLoggingOut(true);
        setAccessMessage(null);
        try {
            const status = await logoutAccessSession();
            setAuthStatus(status);
            setSettingsModalOpen(false);
        } catch (error) {
            setAccessMessage(getAccessErrorMessage(error));
        } finally {
            setIsLoggingOut(false);
        }
    };

    return (
        <div
            className={`${styles.modal} ${settingsModalOpen ? styles.visible : ''}`}
            onClick={handleBackdropClick}
        >
            <div className={styles.panel}>
                <h3 className={styles.title}>⚙️ {t('settings')}</h3>

                <div className={styles.body}>
                <div className={styles.group}>
                    <label className={styles.label}>{t('accessControlTitle')}</label>

                    {isLocalAccess ? (
                        <>
                            {/* 局域网可访问：主开关，置顶。关闭后隐藏全部门禁选项。 */}
                            <div className={styles.accessToggleCard}>
                                <div className={styles.accessToggleCopy}>
                                    <span className={styles.accessToggleTitle}>
                                        {t('lanBindTitle')}
                                        <span className={`${styles.toggleStateTag} ${lanBindEnabled ? styles.toggleStateOn : styles.toggleStateOff}`}>
                                            {lanBindEnabled ? t('toggleStateOn') : t('toggleStateOff')}
                                        </span>
                                    </span>
                                    <p>
                                        {lanBindEnabled ? t('lanBindEnabledHint') : t('lanBindDisabledHint')}
                                    </p>
                                    <p className={styles.fieldHint}>{t('lanBindRestartHint')}</p>
                                </div>
                                <button
                                    type="button"
                                    className={`${styles.toggleSwitch} ${lanBindEnabled ? styles.toggleSwitchOn : ''}`}
                                    onClick={() => setLanBindEnabled(!lanBindEnabled)}
                                    aria-pressed={lanBindEnabled}
                                    aria-label={t('lanBindToggleLabel')}
                                >
                                    <span className={styles.toggleKnob} />
                                </button>
                            </div>

                            {/* 门禁相关设置：仅在局域网可访问时展示 */}
                            {lanBindEnabled && (
                                <div className={styles.accessDetails}>
                                    {/* 门禁开关，隐私风险提示合并进卡片内 */}
                                    <div className={`${styles.accessToggleCard} ${!accessControlEnabled ? styles.accessToggleWarning : ''}`}>
                                        <div className={styles.accessToggleCopy}>
                                            <span className={styles.accessToggleTitle}>
                                                {t('accessControlSwitchTitle')}
                                                <span className={`${styles.toggleStateTag} ${accessControlEnabled ? styles.toggleStateOn : styles.toggleStateOff}`}>
                                                    {accessControlEnabled ? t('toggleStateOn') : t('toggleStateOff')}
                                                </span>
                                            </span>
                                            <p>
                                                {accessControlEnabled ? t('accessControlEnabledHint') : t('accessControlDisabledHint')}
                                            </p>
                                            {!accessControlEnabled && (
                                                <p className={styles.accessRiskNote}>{t('accessControlDisabledWarning')}</p>
                                            )}
                                        </div>
                                        <button
                                            type="button"
                                            className={`${styles.toggleSwitch} ${accessControlEnabled ? styles.toggleSwitchOn : ''}`}
                                            onClick={() => handleAccessControlToggle(!accessControlEnabled)}
                                            aria-pressed={accessControlEnabled}
                                            aria-label={t('accessControlToggleLabel')}
                                        >
                                            <span className={styles.toggleKnob} />
                                        </button>
                                    </div>

                                    {/* 门禁开启后的访问码与会话设置 */}
                                    {accessControlEnabled && (
                                        <div className={styles.accessForm}>
                                            <div className={styles.statusRow}>
                                                <span className={`${styles.statusPill} ${authStatus?.has_access_code ? styles.statusOk : styles.statusWarn}`}>
                                                    {authStatus?.has_access_code ? t('accessCodeConfigured') : t('accessCodeMissing')}
                                                </span>
                                                <span className={styles.statusPill}>
                                                    {t('accessOwnerMode')}
                                                </span>
                                            </div>
                                            {authStatus?.setup_required ? (
                                                <p className={styles.warning}>{t('accessCodeSetupReminder')}</p>
                                            ) : (
                                                <p className={styles.hint}>{t('accessControlHint')}</p>
                                            )}

                                            <div className={styles.inputWrapper}>
                                                <input
                                                    type="password"
                                                    className={styles.input}
                                                    value={accessCode}
                                                    onChange={(e) => setAccessCodeValue(e.target.value)}
                                                    placeholder={t('accessCodePlaceholder')}
                                                    autoComplete="new-password"
                                                />
                                                <button
                                                    type="button"
                                                    className={styles.saveBtn}
                                                    onClick={handleSaveAccessCode}
                                                    disabled={isAccessSaving || accessCode.length < 8}
                                                >
                                                    {t('accessCodeSave')}
                                                </button>
                                            </div>

                                            <div className={styles.inlineGrid}>
                                                <div>
                                                    <label className={styles.label}>{t('sessionDaysLabel')}</label>
                                                    <input
                                                        type="number"
                                                        min={1}
                                                        max={365}
                                                        className={styles.input}
                                                        value={sessionDays}
                                                        onChange={(e) => setSessionDays(Number(e.target.value))}
                                                    />
                                                </div>
                                                <div>
                                                    <label className={styles.label}>{t('remoteGenerationLabel')}</label>
                                                    <div className={styles.segmentedControl}>
                                                        <button
                                                            type="button"
                                                            className={`${styles.segmentBtn} ${!allowRemoteGeneration ? styles.segmentActive : ''}`}
                                                            onClick={() => setAllowRemoteGeneration(false)}
                                                        >
                                                            {t('remoteGenerationOff')}
                                                        </button>
                                                        <button
                                                            type="button"
                                                            className={`${styles.segmentBtn} ${allowRemoteGeneration ? styles.segmentActive : ''}`}
                                                            onClick={() => setAllowRemoteGeneration(true)}
                                                        >
                                                            {t('remoteGenerationOn')}
                                                        </button>
                                                    </div>
                                                    <p className={styles.fieldHint}>{t('remoteGenerationHint')}</p>
                                                </div>
                                            </div>

                                            <div className={styles.securityActions}>
                                                <button
                                                    type="button"
                                                    className={styles.dangerBtn}
                                                    onClick={handleRevokeSessions}
                                                    disabled={isRevokingSessions}
                                                >
                                                    {isRevokingSessions ? t('saving') : t('revokeAllSessions')}
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* 门禁设置保存状态提示（保存动作统一由底部“保存”按钮触发） */}
                            <p className={`${styles.settingState} ${styles.accessStateRow} ${hasAccessSettingsChanges ? styles.settingStatePending : styles.settingStateSaved}`}>
                                {accessSettingsStateText}
                            </p>
                        </>
                    ) : (
                        <>
                            <div className={styles.statusRow}>
                                <span className={`${styles.statusPill} ${authStatus?.access_control_enabled ? styles.statusOk : styles.statusWarn}`}>
                                    {authStatus?.access_control_enabled ? t('accessControlEnabled') : t('accessControlDisabled')}
                                </span>
                                <span className={styles.statusPill}>
                                    {t('accessRemoteMode')}
                                </span>
                            </div>
                            <p className={styles.hint}>
                                {authStatus?.access_control_enabled ? t('accessControlHint') : t('accessControlRemoteDisabledHint')}
                            </p>
                            <div className={styles.securityActions}>
                                <button
                                    type="button"
                                    className={styles.convertBtn}
                                    onClick={handleLogout}
                                    disabled={isLoggingOut || !authStatus?.access_control_enabled}
                                >
                                    {isLoggingOut ? t('saving') : t('logoutCurrentSession')}
                                </button>
                            </div>
                        </>
                    )}
                    {accessMessage ? <p className={styles.message}>{accessMessage}</p> : null}
                </div>

                {isLocalAccess && (
                    <div className={styles.group}>
                        <label className={styles.label}>
                            Workspace Folder ({t('workspaceFolder') || '工作目录'})
                        </label>
                        <div className={styles.inputWrapper}>
                            <input
                                type="text"
                                className={styles.input}
                                value={workspaceFolder}
                                onChange={(e) => setWorkspaceFolder(e.target.value)}
                                placeholder="/path/to/workspace"
                            />
                            <button
                                className={styles.browseBtn}
                                onClick={handleBrowse}
                                title="Browse"
                            >
                                <FolderIcon />
                            </button>
                        </div>
                        <p className={styles.hint}>
                            📁 inputs/ ({t('images') || '图片'}) &nbsp;&nbsp; 📁 outputs/ ({t('models') || '模型'})
                        </p>
                    </div>
                )}

                {isLocalAccess && (
                    <div className={styles.group}>
                        <label className={styles.label}>{t('photoCacheTitle')}</label>
                        <div className={styles.cacheCard}>
                            <div className={styles.cacheHeader}>
                                <div>
                                    <span className={styles.cacheTitle}>{t('photoCacheGenerated')}</span>
                                    <p>{t('photoCacheDescription')}</p>
                                </div>
                                <button
                                    type="button"
                                    className={styles.browseBtn}
                                    onClick={loadPhotoCacheStats}
                                    disabled={isPhotoCacheLoading || isPhotoCacheClearing}
                                >
                                    {isPhotoCacheLoading ? t('loading') : t('photoCacheRefresh')}
                                </button>
                            </div>

                            <div className={styles.cacheStats}>
                                <span>
                                    <strong>{formatCacheSize(photoCacheStats?.indexes.bytes ?? 0)}</strong>
                                    {t('photoCacheIndexes')}
                                </span>
                                <span>
                                    <strong>{formatCacheSize(photoCacheStats?.thumbnails.bytes ?? 0)}</strong>
                                    {t('photoCacheThumbnails')}
                                </span>
                                <span>
                                    <strong>{formatCacheSize(photoCacheStats?.video_posters.bytes ?? 0)}</strong>
                                    {t('photoCachePosters')}
                                </span>
                                <span>
                                    <strong>{formatCacheSize(photoCacheStats?.downloads.bytes ?? 0)}</strong>
                                    {t('photoCacheDownloads')}
                                </span>
                            </div>

                            <div className={styles.cacheFooter}>
                                <span>
                                    {photoCacheStats
                                        ? t('photoCacheTotal', {
                                            files: photoCacheStats.total.files,
                                            size: formatCacheSize(photoCacheStats.total.bytes),
                                        })
                                        : t('photoCacheNotLoaded')}
                                </span>
                                <button
                                    type="button"
                                    className={styles.dangerBtn}
                                    onClick={() => setPhotoCacheConfirmOpen(true)}
                                    disabled={isPhotoCacheLoading || isPhotoCacheClearing}
                                >
                                    {isPhotoCacheClearing ? t('saving') : t('photoCacheClear')}
                                </button>
                            </div>

                            {photoCacheMessage ? <p className={styles.message}>{photoCacheMessage}</p> : null}
                        </div>
                    </div>
                )}

                <div className={styles.group}>
                    <label className={styles.label}>{t('videoReconSettingsTitle')}</label>
                    <div className={styles.cacheCard}>
                        <div className={styles.cacheHeader}>
                            <div>
                                <span className={styles.cacheTitle}>{t('videoReconSettingsDefaults')}</span>
                                <p>{t('videoReconSettingsHint')}</p>
                            </div>
                            <div className={styles.cacheActions}>
                                <button
                                    type="button"
                                    className={styles.browseBtn}
                                    onClick={openVideoReconstructionGuide}
                                >
                                    {t('videoReconOpenGuide')}
                                </button>
                            </div>
                        </div>

                        <div className={styles.videoSettingsGrid}>
                            <div>
                                <label className={styles.labelRow}>
                                    <span>{t('videoReconDefaultQuality')}</span>
                                    <small>{t('videoReconDefaultQualityMeta')}</small>
                                </label>
                                <div className={styles.segmentedControl}>
                                    {(['preview', 'high', 'extreme'] as VideoReconstructionPresetQuality[]).map((quality) => (
                                        <button
                                            key={quality}
                                            type="button"
                                            className={`${styles.segmentBtn} ${styles.segmentBtnStack} ${videoConfig.default_quality === quality ? styles.segmentActive : ''}`}
                                            disabled={!isLocalAccess}
                                            onClick={() => updateVideoConfig({ default_quality: quality })}
                                        >
                                            <span>{t(`videoReconQuality.${quality}`)}</span>
                                            <small>{t(`videoReconQualityMeta.${quality}`)}</small>
                                        </button>
                                    ))}
                                </div>
                                <p className={styles.optionHint}>{t(`videoReconQualityHint.${videoConfig.default_quality}`)}</p>
                            </div>

                            <div>
                                <label className={styles.labelRow}>
                                    <span>{t('videoReconDefaultEngine')}</span>
                                    <small>{t('videoReconDefaultEngineMeta')}</small>
                                </label>
                                <div className={styles.segmentedControl}>
                                    {(['auto', 'stable'] as VideoReconstructionEngine[]).map((engine) => {
                                        const engineDisabled = !isLocalAccess;
                                        return (
                                            <button
                                                key={engine}
                                                type="button"
                                                className={[
                                                    styles.segmentBtn,
                                                    styles.segmentBtnStack,
                                                    videoConfig.default_engine === engine ? styles.segmentActive : '',
                                                    engineDisabled ? styles.segmentDisabled : '',
                                                ].filter(Boolean).join(' ')}
                                                disabled={engineDisabled}
                                                onClick={() => updateVideoConfig({ default_engine: engine })}
                                            >
                                                <span>{t(`videoReconEngine.${engine}`)}</span>
                                                <small>{t(`videoReconEngineMeta.${engine}`)}</small>
                                            </button>
                                        );
                                    })}
                                </div>
                                <p className={styles.optionHint}>{t(`videoReconEngineHint.${videoConfig.default_engine}`)}</p>
                            </div>

                            <div>
                                <label className={styles.labelRow}>
                                    <span>{t('videoReconVramBudget')}</span>
                                    <small>{t('videoReconVramBudgetMeta')}</small>
                                </label>
                                <div className={`${styles.segmentedControl} ${styles.segmentedControlWrap}`}>
                                    {(['auto', '8gb', '12gb', '16gb', '24gb'] as VideoReconstructionVramBudget[]).map((budget) => (
                                        <button
                                            key={budget}
                                            type="button"
                                            className={`${styles.segmentBtn} ${videoConfig.vram_budget === budget ? styles.segmentActive : ''}`}
                                            disabled={!isLocalAccess}
                                            onClick={() => updateVideoConfig({ vram_budget: budget })}
                                        >
                                            {t(`videoReconVram.${budget}`)}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <label className={styles.videoToggleRow}>
                                <span>
                                    <strong>{t('videoReconKeepIntermediate')}</strong>
                                    <small>{t('videoReconKeepIntermediateHint')}</small>
                                </span>
                                <input
                                    type="checkbox"
                                    checked={videoConfig.keep_intermediate_files}
                                    disabled={!isLocalAccess}
                                    onChange={(event) => updateVideoConfig({ keep_intermediate_files: event.target.checked })}
                                />
                            </label>
                        </div>

                        <div className={styles.dependencyList}>
                            {renderDependencyGroup('required', videoDependencies?.required)}
                            {renderDependencyGroup('stable', videoDependencies?.stable)}
                        </div>

                        <div className={styles.dependencyFooter}>
                            <p className={`${styles.settingState} ${hasVideoSettingsChanges ? styles.settingStatePending : styles.settingStateSaved}`}>
                                {hasVideoSettingsChanges ? t('videoReconSettingsUnsaved') : t('videoReconSettingsCurrent')}
                            </p>
                            <button
                                type="button"
                                className={styles.browseBtn}
                                onClick={() => loadVideoReconstructionStatus(true)}
                                disabled={videoStatusLoading}
                            >
                                {videoStatusLoading ? t('loading') : t('videoReconRefreshDiagnostics')}
                            </button>
                        </div>
                        {videoMessage ? <p className={styles.message}>{videoMessage}</p> : null}
                    </div>
                </div>

                {/* Quick Preset */}
                <div className={styles.group}>
                    <label className={styles.label}>
                        {t('quickPresetLabel')}
                    </label>
                    <div className={styles.segmentedControl}>
                        <button
                            className={`${styles.segmentBtn} ${quickPresetMode === 'performance' ? styles.segmentActive : ''}`}
                            onClick={() => handleQuickPresetChange('performance')}
                        >
                            {t('lodPresetPerformance')}
                        </button>
                        <button
                            className={`${styles.segmentBtn} ${quickPresetMode === 'balanced' ? styles.segmentActive : ''}`}
                            onClick={() => handleQuickPresetChange('balanced')}
                        >
                            {t('lodPresetBalanced')}
                        </button>
                        <button
                            className={`${styles.segmentBtn} ${quickPresetMode === 'detail' ? styles.segmentActive : ''}`}
                            onClick={() => handleQuickPresetChange('detail')}
                        >
                            {t('lodPresetDetail')}
                        </button>
                        <button
                            className={`${styles.segmentBtn} ${quickPresetMode === 'manual' ? styles.segmentActive : ''}`}
                            onClick={() => handleQuickPresetChange('manual')}
                        >
                            {t('quickPresetManual')}
                        </button>
                    </div>
                    <p className={styles.hint}>
                        {t('quickPresetHint')}
                    </p>
                </div>

                <div className={styles.group}>
                    <label className={styles.label}>
                        {t('defaultRevealEffectLabel')}
                    </label>
                    <div className={`${styles.segmentedControl} ${styles.segmentedControlWrap}`}>
                        {REVEAL_EFFECT_SETTINGS_OPTIONS.map((effect) => (
                            <button
                                key={effect.id}
                                type="button"
                                className={`${styles.segmentBtn} ${defaultRevealEffect === effect.id ? styles.segmentActive : ''}`}
                                onClick={() => setDefaultRevealEffect(effect.id)}
                            >
                                {t(effect.labelKey)}
                            </button>
                        ))}
                    </div>
                    <p className={styles.hint}>
                        {t('defaultRevealEffectHint')}
                    </p>
                </div>

                {quickPresetMode === 'manual' ? (
                    <>
                        <div className={styles.group}>
                            <label className={styles.label}>{t('advancedSettingsLabel')}</label>
                            <p className={styles.hint}>{t('advancedSettingsHint')}</p>
                        </div>

                        {/* LOD (Level-of-Detail) Toggle */}
                        <div className={styles.group}>
                            <label className={styles.label}>
                                {t('lodLabel')}
                            </label>
                            <div className={styles.segmentedControl}>
                                <button
                                    className={`${styles.segmentBtn} ${!isLodEnabled ? styles.segmentActive : ''}`}
                                    onClick={() => {
                                        if (isLodEnabled) {
                                            applyManualChange(() => {
                                                toggleLod();
                                                reloadCurrentModel();
                                            });
                                        }
                                    }}
                                >
                                    {t('lodOff')}
                                </button>
                                <button
                                    className={`${styles.segmentBtn} ${isLodEnabled ? styles.segmentActive : ''}`}
                                    onClick={() => {
                                        if (!isLodEnabled) {
                                            applyManualChange(() => {
                                                toggleLod();
                                                reloadCurrentModel();
                                            });
                                        }
                                    }}
                                >
                                    {t('lodOn')}
                                </button>
                            </div>
                            <p className={styles.hint}>
                                {t('lodHint')}
                            </p>
                        </div>

                        {/* LOD Presets */}
                        <div className={styles.group}>
                            <label className={styles.label}>
                                {t('lodPresetLabel')}
                            </label>
                            <div className={styles.segmentedControl}>
                                <button
                                    className={`${styles.segmentBtn} ${lodPreset === 'performance' ? styles.segmentActive : ''}`}
                                    onClick={() => applyManualChange(() => setLodPreset('performance'))}
                                >
                                    {t('lodPresetPerformance')}
                                </button>
                                <button
                                    className={`${styles.segmentBtn} ${lodPreset === 'balanced' ? styles.segmentActive : ''}`}
                                    onClick={() => applyManualChange(() => setLodPreset('balanced'))}
                                >
                                    {t('lodPresetBalanced')}
                                </button>
                                <button
                                    className={`${styles.segmentBtn} ${lodPreset === 'detail' ? styles.segmentActive : ''}`}
                                    onClick={() => applyManualChange(() => setLodPreset('detail'))}
                                >
                                    {t('lodPresetDetail')}
                                </button>
                            </div>
                            <p className={styles.hint}>
                                {t('lodPresetHint')}
                            </p>
                        </div>

                        {/* LoD vs non-LoD Comparison */}
                        <div className={styles.group}>
                            <label className={styles.label}>
                                {t('lodCompareLabel')}
                            </label>
                            <div className={styles.segmentedControl}>
                                <button
                                    className={`${styles.segmentBtn} ${lodCompareMode === 'lod' ? styles.segmentActive : ''}`}
                                    onClick={() => applyManualChange(() => setLodCompareMode('lod'))}
                                >
                                    {t('lodCompareLod')}
                                </button>
                                <button
                                    className={`${styles.segmentBtn} ${lodCompareMode === 'non-lod' ? styles.segmentActive : ''} ${(!canCompareLod || !isLodEnabled) ? styles.segmentDisabled : ''}`}
                                    disabled={!canCompareLod || !isLodEnabled}
                                    onClick={() => applyManualChange(() => setLodCompareMode('non-lod'))}
                                >
                                    {t('lodCompareNonLod')}
                                </button>
                            </div>
                            <p className={styles.hint}>
                                {!canCompareLod || !isLodEnabled
                                    ? t('lodCompareUnavailableHint')
                                    : t('lodCompareHint')}
                            </p>
                        </div>

                        {/* RAD Streaming Mode */}
                        <div className={styles.group}>
                            <label className={styles.label}>
                                {t('radModeLabel')}
                            </label>
                            <div className={styles.segmentedControl}>
                                <button
                                    className={`${styles.segmentBtn} ${!radModeEnabled ? styles.segmentActive : ''}`}
                                    onClick={() => {
                                        if (radModeEnabled) {
                                            applyManualChange(() => {
                                                setRadModeEnabled(false);
                                                reloadCurrentModel();
                                            });
                                        }
                                    }}
                                >
                                    {t('radModeOff')}
                                </button>
                                <button
                                    className={`${styles.segmentBtn} ${radModeEnabled ? styles.segmentActive : ''}`}
                                    onClick={() => {
                                        if (!radModeEnabled) {
                                            applyManualChange(() => {
                                                setRadModeEnabled(true);
                                                reloadCurrentModel();
                                            });
                                        }
                                    }}
                                >
                                    {t('radModeOn')}
                                </button>
                            </div>
                            <p className={styles.hint}>
                                {t('radModeHint')}
                            </p>
                        </div>

                        <div className={styles.group}>
                            <label className={styles.label}>
                                {t('radPagedLabel')}
                            </label>
                            <div className={styles.segmentedControl}>
                                <button
                                    className={`${styles.segmentBtn} ${!radPagedEnabled ? styles.segmentActive : ''} ${!radModeEnabled ? styles.segmentDisabled : ''}`}
                                    disabled={!radModeEnabled}
                                    onClick={() => {
                                        if (radPagedEnabled) {
                                            applyManualChange(() => {
                                                setRadPagedEnabled(false);
                                                reloadCurrentModel();
                                            });
                                        }
                                    }}
                                >
                                    {t('radPagedOff')}
                                </button>
                                <button
                                    className={`${styles.segmentBtn} ${radPagedEnabled ? styles.segmentActive : ''} ${!radModeEnabled ? styles.segmentDisabled : ''}`}
                                    disabled={!radModeEnabled}
                                    onClick={() => {
                                        if (!radPagedEnabled) {
                                            applyManualChange(() => {
                                                setRadPagedEnabled(true);
                                                reloadCurrentModel();
                                            });
                                        }
                                    }}
                                >
                                    {t('radPagedOn')}
                                </button>
                            </div>
                            <p className={styles.hint}>
                                {t('radPagedHint')}
                            </p>
                        </div>

                        {/* XR Spark Update Strategy */}
                        <div className={styles.group}>
                            <label className={styles.label}>
                                {t('xrUpdateLabel')}
                            </label>
                            <div className={styles.segmentedControl}>
                                <button
                                    className={`${styles.segmentBtn} ${xrUpdateMode === 'auto' ? styles.segmentActive : ''}`}
                                    onClick={() => applyManualChange(() => setXrUpdateMode('auto'))}
                                >
                                    {t('xrUpdateAuto')}
                                </button>
                                <button
                                    className={`${styles.segmentBtn} ${xrUpdateMode === 'manual' ? styles.segmentActive : ''}`}
                                    onClick={() => applyManualChange(() => setXrUpdateMode('manual'))}
                                >
                                    {t('xrUpdateManual')}
                                </button>
                            </div>
                            <p className={styles.hint}>
                                {t('xrUpdateHint')}
                            </p>
                        </div>

                        {/* High Fidelity Toggle */}
                        <div className={styles.group}>
                            <label className={styles.label}>
                                {t('highFidelityLabel')}
                            </label>
                            <div className={styles.segmentedControl}>
                                <button
                                    className={`${styles.segmentBtn} ${!isHighFidelity ? styles.segmentActive : ''}`}
                                    onClick={() => {
                                        if (isHighFidelity) {
                                            applyManualChange(() => {
                                                toggleHighFidelity();
                                                reloadCurrentModel();
                                            });
                                        }
                                    }}
                                >
                                    {t('hfOff')}
                                </button>
                                <button
                                    className={`${styles.segmentBtn} ${isHighFidelity ? styles.segmentActive : ''}`}
                                    onClick={() => {
                                        if (!isHighFidelity) {
                                            applyManualChange(() => {
                                                toggleHighFidelity();
                                                reloadCurrentModel();
                                            });
                                        }
                                    }}
                                >
                                    {t('hfOn')}
                                </button>
                            </div>
                            <p className={styles.hint}>
                                {t('hfHint')}
                            </p>
                        </div>
                    </>
                ) : (
                    <div className={styles.group}>
                        <p className={styles.hint}>{t('advancedSettingsAutoHint')}</p>
                    </div>
                )}

                {/* Model Format Preference */}
                <div className={styles.group}>
                    <label className={styles.label}>
                        {t('modelFormatLabel')}
                    </label>
                    <div className={styles.segmentedControl}>
                        <button
                            className={`${styles.segmentBtn} ${modelFormat === 'spz' ? styles.segmentActive : ''}`}
                            onClick={() => setModelFormat('spz')}
                        >
                            SPZ {t('formatCompact')}
                        </button>
                        <button
                            className={`${styles.segmentBtn} ${modelFormat === 'ply' ? styles.segmentActive : ''}`}
                            onClick={() => setModelFormat('ply')}
                        >
                            PLY {t('formatOriginal')}
                        </button>
                    </div>
                    <p className={styles.hint}>
                        {t('modelFormatHint')}
                    </p>
                </div>

                {/* Batch Convert */}
                <div className={styles.group}>
                    <button
                        className={styles.convertBtn}
                        onClick={handleConvertAll}
                        disabled={isConverting}
                    >
                        {isConverting ? '⏳ ' + t('converting') : '📦 ' + t('convertAllToSpz')}
                    </button>
                </div>

                {isLocalAccess && workspaceFolder !== originalWorkspace && (
                    <p className={styles.warning}>
                        ⚠️ {t('settingsRestartWarning') || '修改工作目录后需重启服务器生效'}
                    </p>
                )}

                </div>

                <div className={styles.actions}>
                    <button className={styles.cancelBtn} onClick={handleClose}>
                        {t('cancel')}
                    </button>
                    <button
                        className={styles.saveBtn}
                        onClick={handleSave}
                        disabled={isSaving}
                    >
                        {isSaving ? '...' : t('save')}
                    </button>
                </div>

                <ConfirmDialog
                    isOpen={photoCacheConfirmOpen}
                    title={t('photoCacheClear')}
                    message={t('photoCacheClearConfirm')}
                    confirmLabel={t('photoCacheClear')}
                    isBusy={isPhotoCacheClearing}
                    danger
                    onConfirm={handleClearPhotoCache}
                    onClose={() => setPhotoCacheConfirmOpen(false)}
                />
            </div>
        </div>
    );
};

function formatCacheSize(bytes: number): string {
    if (!Number.isFinite(bytes) || bytes <= 0) {
        return '0 B';
    }
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let value = bytes;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
        value /= 1024;
        unitIndex += 1;
    }
    return `${value >= 10 || unitIndex === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unitIndex]}`;
}
