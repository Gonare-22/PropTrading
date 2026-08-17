# VPS Setup for 24/7 Algo Trading (Optional)

If you want your EA to run 24/7 without keeping your personal computer on, you need a VPS (Virtual Private Server).

---

## Why Use a VPS?

**Problems without VPS:**
- ❌ Your computer must stay on 24/7
- ❌ Power outages = missed trades
- ❌ Internet disconnection = EA stops
- ❌ Windows updates = computer restart = EA stops
- ❌ High electricity cost

**Benefits with VPS:**
- ✅ EA runs 24/7 even when your PC is off
- ✅ No power/internet issues
- ✅ Low latency to broker servers
- ✅ Cost: $10-30/month
- ✅ Access from anywhere (phone, tablet, laptop)

---

## VPS Options

### Option 1: MT5 Built-in VPS (Easiest)

**Cost:** $15-30/month  
**Setup Time:** 5 minutes  
**Pros:** Seamless integration, one-click setup  
**Cons:** More expensive than alternatives  

**How to Setup:**

1. In MT5, click **Tools → Options → VPS**
2. Click **"Migrate to MetaTrader VPS"**
3. Choose subscription plan (1 month, 3 months, 12 months)
4. Pay via MetaQuotes
5. Wait 5 minutes for VPS to activate
6. Click **"Enable"**
7. MT5 uploads your EA, settings, and charts to VPS
8. You can close MT5 on your PC — EA runs on VPS!

**To verify:**
- VPS tab shows "Enabled" status
- You can now close MT5 on your computer
- EA continues running on VPS

### Option 2: External VPS (Cheaper)

**Cost:** $5-15/month  
**Setup Time:** 30 minutes  
**Pros:** Cheaper, more control  
**Cons:** Manual setup required  

**Recommended Providers:**

1. **Forex VPS Providers (Optimized for MT5):**
   - BeeksFX: https://www.beeksfx.com/ (~$15/month)
   - FXVM: https://www.fxvm.com/ (~$28/month)
   - VPSForex: https://www.vpsforex.com/ (~$20/month)

2. **General VPS Providers (Cheaper):**
   - Vultr: https://www.vultr.com/ (~$6/month)
   - DigitalOcean: https://www.digitalocean.com/ (~$6/month)
   - Contabo: https://contabo.com/ (~$5/month)

**Setup Steps (General VPS):**

1. **Sign up for VPS:**
   - Choose Windows Server (not Linux)
   - Minimum: 2GB RAM, 40GB disk, 1 CPU core
   - Location: Near your broker's server (for low latency)

2. **Connect to VPS:**
   - Download Remote Desktop Connection (built into Windows)
   - Open Remote Desktop
   - Enter VPS IP address
   - Enter username/password (from VPS provider)
   - Click Connect

3. **Install MT5 on VPS:**
   - Inside VPS, open browser
   - Download MT5 from broker's website
   - Install MT5
   - Login with your demo/live account

4. **Transfer EA to VPS:**
   - Copy `EMA_Crossover_Strategy.mq5` from your PC
   - Paste into VPS MT5: `File → Open Data Folder → MQL5 → Experts`
   - Compile EA in VPS MetaEditor (F7)

5. **Setup EA on VPS:**
   - Follow LIVE_TRADING_SETUP_GUIDE.md steps
   - Attach EA to chart
   - Enable AutoTrading
   - Verify EA is running

6. **Disconnect:**
   - Close Remote Desktop
   - EA continues running on VPS!

**To check EA later:**
- Connect to VPS via Remote Desktop
- Open MT5
- Check Terminal for trades

---

## Cost Comparison

| Option | Cost/Month | Setup Difficulty | Best For |
|--------|-----------|------------------|----------|
| Keep PC on 24/7 | $5-20 (electricity) | Easy | Testing (1-2 weeks) |
| MT5 Built-in VPS | $15-30 | Very Easy | Beginners |
| External VPS | $5-15 | Medium | Cost-conscious traders |

---

## Do You Need a VPS?

**Use VPS if:**
- ✅ You want to trade 24/7 without keeping PC on
- ✅ You have unreliable power/internet
- ✅ You're serious about algo trading
- ✅ You want low-latency to broker

**Don't need VPS if:**
- ❌ Just testing (first 1-2 weeks)
- ❌ Trading only during specific hours
- ❌ Your PC is always on anyway
- ❌ Testing on demo before committing

---

## Recommendation

### First 2 Weeks: No VPS
- Test EA on your PC
- Keep MT5 running during market hours
- Verify EA works correctly
- Check results

### After 2 Weeks: Get VPS
- If EA performs well, get VPS
- Start with MT5 built-in VPS (easy) or external VPS (cheap)
- Migrate EA to VPS
- Monitor remotely

---

## VPS Checklist

Before buying VPS:
- [ ] EA tested for 2+ weeks on PC
- [ ] EA is profitable (or showing promise)
- [ ] You understand how EA works
- [ ] You've chosen VPS provider
- [ ] VPS location is near broker server
- [ ] VPS has Windows Server OS
- [ ] VPS has at least 2GB RAM

After setting up VPS:
- [ ] MT5 installed on VPS
- [ ] EA compiled on VPS
- [ ] EA attached to chart on VPS
- [ ] AutoTrading enabled on VPS
- [ ] EA running (check smiley face)
- [ ] Verified trades opening/closing correctly
- [ ] Can access VPS remotely

---

## Alternative: MT5 Web Terminal (Not Recommended)

MT5 Web Terminal runs in browser, but:
- ❌ EAs don't work in web terminal
- ❌ Only for manual trading
- ❌ Not suitable for algo trading

**For algo trading, you MUST use:**
- Desktop MT5 on your PC (for testing)
- Desktop MT5 on VPS (for 24/7 trading)

---

## Summary

**For Testing (First 2-4 Weeks):**
```
Run EA on your PC
→ Keep MT5 open during trading hours
→ Monitor performance
→ Verify EA works correctly
```

**For Live Trading (After Testing):**
```
Get VPS
→ Option 1: MT5 built-in VPS ($15-30/month, easy)
→ Option 2: External VPS ($5-15/month, cheaper)
→ Migrate EA to VPS
→ Trade 24/7 without keeping PC on
```

**My Recommendation:**
1. Test on PC for 2-4 weeks (no VPS needed)
2. If profitable, get external VPS (Vultr/DigitalOcean = $6/month)
3. Install MT5 on VPS, transfer EA, run 24/7

---

## Need Help?

- MT5 VPS: https://www.mql5.com/en/vps
- Vultr Guide: Search "Vultr Windows VPS MT5 setup"
- VPS Comparison: https://www.forexvps.net/

Good luck! 🚀
