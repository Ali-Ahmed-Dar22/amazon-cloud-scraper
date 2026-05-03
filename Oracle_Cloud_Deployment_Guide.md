#  Oracle Cloud Deployment Guide: 24/7 Python Scripts

*A complete, step-by-step guide to deploying a Python web scraper to an Oracle Cloud "Always Free" Linux Server.*

---

##  Phase 1: Set Up the Network (VCN)

Before creating a server, you must create a network with internet access.

1. **Go to Virtual Cloud Networks (VCN)**

   - Click the **☰ Menu** (top-left) → **Networking** → **Virtual Cloud Networks**.
   - Click the blue **Create VCN** button.
   - **Name:** `myvcn`
   - **IPv4 CIDR Block:** `10.0.0.0/16`
   - Check the box for **"Use DNS Hostnames"**.
   - Click **Create VCN**.
2. **Create an Internet Gateway**

   - Inside your new VCN page, click **Internet Gateways** on the left menu.
   - Click **Create Internet Gateway**.
   - **Name:** `mygateway`
   - Click **Create**.
3. **Update the Route Table**

   - Click **Route Tables** on the left menu.
   - Click on the **Default Route Table**.
   - Click **Add Route Rules**.
   - **Target Type:** `Internet Gateway`
   - **Destination CIDR Block:** `0.0.0.0/0`
   - **Target Internet Gateway:** select `mygateway`
   - Click **Add Route Rules**.
4. **Create a Public Subnet**

   - Click **Subnets** on the left menu.
   - Click **Create Subnet**.
   - **Name:** `mypublicsubnet`
   - **Subnet Type:** `Regional`
   - **IPv4 CIDR Block:** `10.0.0.0/24`
   - **Route Table:** select the Default Route Table.
   - **Subnet Access:**  Select **Public Subnet**.
   - Click **Create Subnet**.

---

##  Phase 2: Create the Server (Instance)

Now, create the actual Linux computer.

1. **Go to Instances**

   - Click **☰ Menu** → **Compute** → **Instances**.
   - Click **Create instance**.
   - **Name:** `amazon-scraper` (or your preferred name).
2. **Select the Operating System**

   - In the "Image and shape" section, click **Edit**.
   - Change the image to **Ubuntu 22.04**.
   - Keep the shape as default (VM.Standard.E2.1.Micro - Always Free).
3. **Configure Networking**

   - In the "Networking" section, select **Select existing virtual cloud network**.
   - **VCN:** select `myvcn`.
   - **Subnet:** select `mypublicsubnet`.
   - **Public IPv4 address:** Toggle it **ON** (Automatically assign public IPv4 address).
4. **Save Your SSH Key (Crucial!)**

   - In the "Add SSH keys" section, select **Generate a key pair for me**.
   - Click **Download private key**.
   -  Save this `.key` file directly to your **Desktop**. You cannot download it later!
5. **Create**

   - Click the **Create** button at the bottom.
   - Wait 2-3 minutes. When the status turns green (**RUNNING**), copy the **Public IP Address** (e.g., `51.170.87.231`).

---

##  Phase 3: Connect to Your Server

Use Windows PowerShell to log into your cloud server.

1. **Fix Key Permissions (First Time Only)**

   - Open **PowerShell** on your Windows PC.
   - Run this command to secure your key (replace the filename with your actual key name):
     ```powershell
     icacls "C:\Users\hp\Desktop\ssh-key-2026-04-28.key" /inheritance:r /grant:r "%USERNAME%:(R)"
     ```
2. **Connect via SSH**

   - In PowerShell, run the connection command (replace your key name and IP):
     ```powershell
     ssh -i "C:\Users\hp\Desktop\ssh-key-2026-04-28.key" ubuntu@YOUR_SERVER_IP
     ```
   - Type `yes` when prompted. You will now see `ubuntu@amazon-scraper:~$`, meaning you are inside the server!

---

##  Phase 4: Prepare the Server

Install Google Chrome and Python libraries on the blank server.

Run these commands **one by one** in your SSH terminal:

1. **Update the server:**

   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

   *(If a pink popup appears asking about restarting services, just press **Enter**).*
2. **Install basic tools:**

   ```bash
   sudo apt install -y python3-pip tmux wget curl
   ```
3. 
   **Download Google Chrome:**

   ```bash
   wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
   ```
4. **Install Google Chrome:**

   ```bash
   sudo apt install -y ./google-chrome-stable_current_amd64.deb
   ```
5. **Install Python Libraries:**

   ```bash
   pip3 install undetected-chromedriver selenium requests beautifulsoup4
   ```

---

##  Phase 5: Upload Your Python Script

Move the script from your Windows PC to the Cloud Server.

1. Open a **brand new** PowerShell window (keep the server window open).
2. Use the `scp` command to upload the file (replace paths, key name, and IP):
   ```powershell
   scp -i "C:\Users\hp\Desktop\ssh-key-2026-04-28.key" "C:\Users\hp\Desktop\N.K\amazon\Final_testing_cloud.py" ubuntu@YOUR_SERVER_IP:~/
   ```
3. Go back to your Server window and type `ls`. You should see `Final_testing_cloud.py` listed.

---

##  Phase 6: Run the Script 24/7 (The Magic Step)

We use `tmux` to create a virtual window that stays alive even when your PC is turned off.

1. **Start a tmux session:**

   ```bash
   tmux new -s scraper
   ```
2. **Run your script:**

   ```bash
   python3 Final_testing_cloud.py
   ```
3. **Safely Leave it Running (Detach):**

   - Press and hold **`Ctrl`**, then tap **`b`**.
   - Let go of both keys.
   - Tap **`d`**.
   - *You will see `[detached]`. You can now safely close PowerShell and turn off your computer!*

---

##  How to Check on Your Script Later

To see the live output of your script tomorrow or next week:

1. Open **PowerShell** and connect to the server:
   ```powershell
   ssh -i "C:\Users\hp\Desktop\ssh-key-2026-04-28.key" ubuntu@YOUR_SERVER_IP
   ```
2. Re-attach to the virtual window:
   ```bash
   tmux attach -t scraper
   ```
3. When you are done looking, **always Detach** safely (`Ctrl + B`, then `D`).
   -  *Never press `Ctrl + C` unless you want to permanently stop the script.*
