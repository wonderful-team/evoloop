import { useTranslation } from 'react-i18next'
import { Sparkles, Crown, ArrowRight } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@evoloop/shared/components/ui/dialog'
import { Button } from '@evoloop/shared/components/ui/button'
import { Badge } from '@evoloop/shared/components/ui/badge'
import { useBenefitStore, PLAN_KEY_MAP } from '@/stores/benefitStore'

export function BenefitRequirementDialog() {
  const { t } = useTranslation()
  const { isOpen, info, closeDialog } = useBenefitStore()

  if (!info) return null

  const planKey = PLAN_KEY_MAP[info.requiredPlan || ''] || info.requiredPlan
  const planName = t(`subscription.plans.${planKey}`, {
    defaultValue: info.requiredPlan || t('subscription.plans.higher')
  })
  const benefitName = t(`subscription.benefits.${info.feature}`, {
    defaultValue: info.featureName || info.feature || t('subscription.errors.featureFallback')
  })

  const handleUpgrade = () => {
    window.location.hash = '#/subscription'
    closeDialog()
  }

  return (
    <Dialog open={isOpen} onOpenChange={closeDialog}>
      <DialogContent className="sm:max-w-[450px] p-0 overflow-hidden border-none shadow-2xl bg-slate-950/95 backdrop-blur-xl">
        <div className="absolute top-0 right-0 w-64 h-64 bg-primary/10 blur-[100px] rounded-full -mr-32 -mt-32 pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-64 h-64 bg-purple-500/10 blur-[100px] rounded-full -ml-32 -mb-32 pointer-events-none" />

        <div className="relative p-8 flex flex-col items-center text-center space-y-6">
          <div className="relative">
            <div className="absolute -inset-4 bg-primary/20 rounded-full blur-2xl animate-pulse" />
            <div className="relative h-20 w-20 bg-gradient-to-br from-primary to-purple-600 rounded-3xl flex items-center justify-center shadow-2xl border border-white/20">
              <Crown className="h-10 w-10 text-white" />
            </div>
          </div>

          <div className="space-y-2">
            <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest">
               {t('subscription.status.locked')}
            </Badge>
            <DialogTitle className="text-2xl font-bold tracking-tight text-white pt-2">
              {t('subscription.errors.dialogTitle', { feature: benefitName })}
            </DialogTitle>
            <DialogDescription className="text-slate-400 text-sm max-w-[320px] mx-auto leading-relaxed">
              {info.message || t('subscription.errors.benefitDescription', { feature: planName })}
            </DialogDescription>
          </div>

          <div className="w-full pt-4 space-y-3">
            <Button
              className="w-full h-12 rounded-xl bg-gradient-to-r from-primary to-purple-600 hover:from-primary/90 hover:to-purple-600/90 text-white font-bold text-base shadow-lg shadow-primary/20 transition-all hover:scale-[1.02] active:scale-[0.98] group"
              onClick={handleUpgrade}
            >
              <Sparkles className="mr-2 h-5 w-5 animate-pulse" />
              {t('subscription.errors.upgradeAction')}
              <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Button>
            <Button
              variant="ghost"
              className="w-full text-slate-500 hover:text-slate-300 hover:bg-white/5 font-medium"
              onClick={closeDialog}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
