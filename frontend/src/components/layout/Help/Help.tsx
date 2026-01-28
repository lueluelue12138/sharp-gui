import React, { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import * as Icons from '@/components/common/Icons';
import styles from './Help.module.css';

export const Help: React.FC = () => {
    const { t } = useTranslation();
    const [isOpen, setIsOpen] = useState(false);
    const panelRef = useRef<HTMLDivElement>(null);

    return (
        <>
            {/* Help Button */}
            <button 
                className={styles.helpBtn} 
                onClick={() => setIsOpen(!isOpen)}
                title={t("controls_help")}
            >
                <Icons.HelpIcon />
            </button>

            {/* Help Panel */}
            <div className={`${styles.helpPanel} ${isOpen ? styles.visible : ''}`} ref={panelRef}>
                <h4>{t("helpTitle")}</h4>
                
                <div className={styles.helpItem}>
                    <div className={styles.helpIcon}>
                        <Icons.JoystickIcon /> {/* Approximation for Drag/Touch icon */}
                    </div>
                    <div><b>{t("helpDrag")}</b> - {t("helpDragDesc")}</div>
                </div>

                <div className={styles.helpItem}>
                    <div className={styles.helpIcon}>
                         {/* Click/Target Icon approximation */}
                         <Icons.CheckIcon /> 
                    </div>
                    <div><b>{t("helpClick")}</b> - {t("helpClickDesc")}</div>
                </div>

                 <div className={styles.helpItem}>
                    <div className={styles.helpIcon}>
                        <Icons.View360Icon />
                    </div>
                    <div><b>{t("helpLeftRight")}</b> - {t("helpLeftRightDesc")}</div>
                </div>

                 <div className={styles.helpItem}>
                    <div className={styles.helpIcon}>
                         <Icons.FullscreenIcon /> {/* Approx for Zoom */}
                    </div>
                    <div><b>{t("helpScroll")}</b> - {t("helpScrollDesc")}</div>
                </div>

                 {/* TODO: Add more items as per original HTML if needed, mapping to available icons or adding new ones. 
                     For now covering basics.
                 */}
                  <div className={styles.helpItem}>
                    <div className={styles.helpIcon}>
                        <Icons.GyroIcon />
                    </div>
                    <div><b>{t("helpGyro")}</b> - {t("helpGyroDesc")}</div>
                </div>

                 <div className={styles.helpItem}>
                    <div className={styles.helpIcon}>
                        <Icons.View360Icon />
                    </div>
                    <div><b>{t("helpFrontView")}</b> - {t("helpFrontViewDesc")}</div>
                </div>

                <div className={styles.helpItem}>
                    <div className={styles.helpIcon}>
                        <Icons.JoystickIcon />
                    </div>
                    <div><b>{t("helpWASD")}</b> - {t("helpWASDDesc")}</div>
                </div>

                 <div className={styles.helpItem}>
                    <div className={styles.helpIcon}>
                        <Icons.JoystickIcon />
                    </div>
                    <div dangerouslySetInnerHTML={{ __html: t("helpSpeedMode") }} />
                </div>

                {/* Virtual Joystick (Mobile) */}
                <div className={styles.helpItem}>
                    <div className={styles.helpIcon}>
                        <Icons.JoystickIcon />
                    </div>
                    <div><b>{t("helpJoystick")}</b> - {t("helpJoystickDesc")}</div>
                </div>

                {/* VR Mode */}
                <div className={styles.helpItem}>
                    <div className={styles.helpIcon}>
                        <Icons.VRIcon />
                    </div>
                    <div><b>{t("helpVR")}</b> - {t("helpVRDesc")}</div>
                </div>

                <div className={styles.helpItem}>
                    <div className={styles.helpIcon}>
                        <Icons.JoystickIcon />
                    </div>
                    <div><b>{t("helpVRJoystick")}</b> - {t("helpVRJoystickDesc")}</div>
                </div>
            </div>
        </>
    );
};
