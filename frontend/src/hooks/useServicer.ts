
import { useQuery } from "@tanstack/react-query";
import { EvoLoopApi } from "@/client/evoloopClient";
import useCustomToast from "./useCustomToast";

type Platform = 'mobile' | 'desktop';

export const useServicer = (platform: Platform = 'desktop') => {
    const { showErrorToast } = useCustomToast();

    const { data: config, isLoading } = useQuery({
        queryKey: ['servicerConfig'],
        queryFn: EvoLoopApi.getServicerConfig,
        staleTime: 1000 * 60 * 60, // 1 hour
    });

    const handleContactSupport = () => {
        if (!config) return;

        let url = '';


        if (platform === 'mobile') {
            // Priority: H5 config
            const h5 = config.h5;
            if (h5?.type === 'wxwork') {
                url = h5.wxwork_url;
            } else if (h5?.type === 'third') {
                url = h5.third_url;
            }
        } else {
            // Desktop
            // Priority: PC config -> H5 config (fallback for WxWork)
            const pc = config.pc;
            const h5 = config.h5;

            if (pc?.type === 'third') {
                url = pc.third_url;
            } else if (h5?.type === 'wxwork') {
                // Fallback to H5 Enterprise WeChat if PC is not configured or User prefers WxWork availablity
                // Check if user explicitly wants this behavior. Usually safe to fallback.
                url = h5.wxwork_url;
            } else if (h5?.type === 'third' && pc?.type === 'none') {
                // Fallback to H5 Third Party if PC is none
                url = h5.third_url;
            }
        }

        if (url) {
            window.open(url, '_blank');
        } else {
            showErrorToast('Support not configured.');
        }
    };

    const hasSupport = () => {
        if (!config) return false;

        if (platform === 'mobile') {
            return config.h5?.type === 'wxwork' || config.h5?.type === 'third';
        } else {
            const pcHas = config.pc?.type === 'third';
            const h5Has = config.h5?.type === 'wxwork' || config.h5?.type === 'third';
            return pcHas || h5Has;
        }
    };

    return {
        config,
        isLoading,
        handleContactSupport,
        hasSupport: hasSupport()
    };
};
