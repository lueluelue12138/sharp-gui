import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { useAppStore } from '@/store/useAppStore';
import styles from './GyroIndicator.module.css';

interface GyroIndicatorProps {
    ballRef: React.RefObject<HTMLDivElement | null>;
}

export const GyroIndicator: React.FC<GyroIndicatorProps> = ({ ballRef }) => {
    const { isGyroEnabled } = useAppStore();
    const { t } = useTranslation();
    const [showHint, setShowHint] = useState(false);

    useEffect(() => {
        if (isGyroEnabled) {
            setShowHint(true);
            const timer = setTimeout(() => setShowHint(false), 2500);
            return () => clearTimeout(timer);
        } else {
            setShowHint(false);
        }
    }, [isGyroEnabled]);

    if (!isGyroEnabled) return null;

    return createPortal(
        <>
            {/* Hint */}
            <div className={`${styles.hint} ${showHint ? styles.show : ''}`}>
                {t("gyroHint")}
            </div>

            {/* Indicator */}
            <div className={`${styles.indicator} ${isGyroEnabled ? styles.visible : ''} ${isGyroEnabled ? styles.active : ''}`}>
                <div ref={ballRef} className={styles.ball} />
                <div className={styles.crosshair} />
            </div>
        </>,
        document.body
    );
};
