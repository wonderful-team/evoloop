import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Phone, ShieldCheck, Loader2 } from 'lucide-react';
import { Button } from '@evoloop/shared/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@evoloop/shared/components/ui/form';
import { Input } from '@evoloop/shared/components/ui/input';
import { LoadingButton } from '@evoloop/shared/components/ui/loading-button';
import useAuth from '@/hooks/useAuth';

const createSchema = (t: any) =>
  z.object({
    mobile: z.string().regex(/^1[3-9]\d{9}$/, {
      message: t('auth.errors.invalidMobile'),
    }),
    code: z.string().length(6, {
      message: t('auth.errors.invalidCode'),
    }),
  });

type FormData = z.infer<ReturnType<typeof createSchema>>;

interface MobileLoginProps {
  onSuccess?: () => void;
}

export function MobileLogin({ onSuccess }: MobileLoginProps) {
  const { t } = useTranslation();
  const { loginMobileMutation, requestMobileCodeMutation } = useAuth();
  const [countdown, setCountdown] = useState(0);
  const [verificationKey, setVerificationKey] = useState<string | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const formSchema = createSchema(t);
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: 'onBlur',
    defaultValues: {
      mobile: '',
      code: '',
    },
  });

  const mobileValue = form.watch('mobile');
  const isMobileValid = /^1[3-9]\d{9}$/.test(mobileValue);

  // Countdown timer effect
  useEffect(() => {
    if (countdown > 0) {
      timerRef.current = setTimeout(() => setCountdown(countdown - 1), 1000);
    } else {
      if (timerRef.current) clearTimeout(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [countdown]);

  const handleSendCode = async () => {
    if (!isMobileValid || countdown > 0) return;

    try {
      const response = await requestMobileCodeMutation.mutateAsync({
        mobile: mobileValue,
      });
      
      // In Member Center responses, the key is usually in data.key
      // based on our AccountService.requestMobileCode wrapping
      const data = (response as any);
      if (data.key) {
        setVerificationKey(data.key);
      } else if (data.data?.key) {
        setVerificationKey(data.data.key);
      }
      
      setCountdown(60);
    } catch (error) {
      console.error('Failed to send code:', error);
    }
  };

  const onSubmit = async (data: FormData) => {
    if (!verificationKey) {
      // If we don't have a key, we might need to show an error or re-request code
      return;
    }

    try {
      await loginMobileMutation.mutateAsync({
        mobile: data.mobile,
        code: data.code,
        key: verificationKey,
      });
      onSuccess?.();
    } catch (error) {
      console.error('Mobile login failed:', error);
    }
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="mobile"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('auth.login.mobile')}</FormLabel>
              <div className="relative">
                <Phone className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <FormControl>
                  <Input
                    placeholder={t('auth.login.mobilePlaceholder')}
                    className="pl-9"
                    {...field}
                  />
                </FormControl>
              </div>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="code"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('auth.login.code')}</FormLabel>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <ShieldCheck className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <FormControl>
                    <Input
                      placeholder={t('auth.login.codePlaceholder')}
                      className="pl-9"
                      maxLength={6}
                      {...field}
                    />
                  </FormControl>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  className="w-32"
                  disabled={!isMobileValid || countdown > 0 || requestMobileCodeMutation.isPending}
                  onClick={handleSendCode}
                >
                  {requestMobileCodeMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : countdown > 0 ? (
                    `${countdown}s`
                  ) : (
                    t('auth.login.getCode')
                  )}
                </Button>
              </div>
              <FormMessage />
            </FormItem>
          )}
        />

        <LoadingButton
          type="submit"
          className="w-full"
          loading={loginMobileMutation.isPending}
          disabled={!verificationKey}
        >
          {t('auth.login.submit')}
        </LoadingButton>
      </form>
    </Form>
  );
}
