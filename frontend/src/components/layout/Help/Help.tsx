import React, { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import * as Icons from '@/components/common/Icons';
import { useAppStore } from '@/store/useAppStore';
import styles from './Help.module.css';

interface HelpEntry {
    icon: React.ReactNode;
    label: string;
    desc: string;
    html?: boolean;
}

interface HelpCategory {
    title: string;
    items: HelpEntry[];
}

interface HelpProps {
    showCloseModel?: boolean;
}

export const Help: React.FC<HelpProps> = ({ showCloseModel = false }) => {
    const { t } = useTranslation();
    const [isOpen, setIsOpen] = useState(false);
    const panelRef = useRef<HTMLDivElement>(null);
    const currentModelUrl = useAppStore((state) => state.currentModelUrl);
    const setCurrentModel = useAppStore((state) => state.setCurrentModel);

    const categories: HelpCategory[] = [
        {
            title: t('helpCatGeneral'),
            items: [
                { icon: <Icons.JoystickIcon />, label: t('helpDrag'), desc: t('helpDragDesc') },
                { icon: <Icons.CheckIcon />, label: t('helpClick'), desc: t('helpClickDesc') },
                { icon: <Icons.FullscreenIcon />, label: t('helpScroll'), desc: t('helpScrollDesc') },
                { icon: <Icons.View360Icon />, label: t('helpFrontView'), desc: t('helpFrontViewDesc') },
            ],
        },
        {
            title: t('helpCatDesktop'),
            items: [
                { icon: <Icons.View360Icon />, label: t('helpLeftRight'), desc: t('helpLeftRightDesc') },
                { icon: <Icons.JoystickIcon />, label: t('helpWASD'), desc: t('helpWASDDesc') },
                { icon: <Icons.JoystickIcon />, label: '', desc: t('helpSpeedMode'), html: true },
                { icon: <Icons.ResetIcon />, label: t('helpResetKey'), desc: t('helpResetKeyDesc') },
            ],
        },
        {
            title: t('helpCatMobile'),
            items: [
                { icon: <Icons.GyroIcon />, label: t('helpGyro'), desc: t('helpGyroDesc') },
                { icon: <Icons.JoystickIcon />, label: t('helpJoystick'), desc: t('helpJoystickDesc') },
            ],
        },
        {
            title: t('helpCatXR'),
            items: [
                { icon: <Icons.VRIcon />, label: t('helpVR'), desc: t('helpVRDesc') },
                { icon: <Icons.ARIcon />, label: t('helpAR'), desc: t('helpARDesc') },
                { icon: <Icons.JoystickIcon />, label: t('helpVRJoystick'), desc: t('helpVRJoystickDesc') },
                { icon: <Icons.ResetIcon />, label: t('helpVRReset'), desc: t('helpVRResetDesc') },
            ],
        },
    ];

    return (
        <>
            {showCloseModel && currentModelUrl ? (
                <button
                    className={styles.closeBtn}
                    onClick={() => setCurrentModel(null, null)}
                    aria-label={t('closeModel')}
                    data-tooltip={t('closeModel')}
                    type="button"
                >
                    <Icons.CloseIcon />
                </button>
            ) : null}
            <button
                className={styles.helpBtn}
                onClick={() => setIsOpen(!isOpen)}
                title={t('controls_help')}
            >
                <Icons.HelpIcon />
            </button>

            <div className={`${styles.helpPanel} ${isOpen ? styles.visible : ''}`} ref={panelRef}>
                <h4>{t('helpTitle')}</h4>

                {categories.map((cat) => (
                    <div key={cat.title} className={styles.helpCategory}>
                        <div className={styles.categoryHeader}>{cat.title}</div>
                        {cat.items.map((item, i) => (
                            <div key={i} className={styles.helpItem}>
                                <div className={styles.helpIcon}>{item.icon}</div>
                                {item.html ? (
                                    <div dangerouslySetInnerHTML={{ __html: item.desc }} />
                                ) : (
                                    <div><b>{item.label}</b> - {item.desc}</div>
                                )}
                            </div>
                        ))}
                    </div>
                ))}
            </div>
        </>
    );
};
