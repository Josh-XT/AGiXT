#!/bin/bash
# Script to update the timezone in specified AGiXT Docker Compose files to the current server timezone.

# Determine the current server timezone
current_timezone=$(timedatectl | awk '/Time zone/ {print $3}')

# Function to replace the timezone in a file
replace_timezone() {
    local file="$1"
    # Use sed to replace the timezone pattern in the file
    sed -i "s|TZ=\${TZ-[^}]*}|TZ=\${TZ-$current_timezone}|g" "$file"
}

# Array of files to be updated
compose_files=("docker-compose.yml" "docker-compose-dev.yml"  "docker-compose-local-nvidia.yml" "docker-compose-local-nvidia-sd.yml")

# Update each file in the array
for file in "${compose_files[@]}"; do
    replace_timezone "$file"
done

# Display a message indicating successful update
echo "Timezone in files successfully updated to the current server timezone: $current_timezone"



# Explanation of the script:

# Determine Current Timezone:
# Use timedatectl to retrieve information about the current server timezone.
# awk extracts the timezone information from the output.

# Function to Replace Timezone:
# Define a function replace_timezone that takes a file as an argument and uses sed to replace the timezone pattern in the file.
# The pattern TZ=${TZ-[^}]*} matches strings like TZ=${TZ-America/New_York} or similar.

# Array of Files:
# Create an array compose_files containing the names of Docker Compose files to be updated.

# Update Each File:
# Iterate through the array of files and call the replace_timezone function for each file.

# Display Success Message:
# Print a message indicating that the timezone in the files has been successfully updated to the current server timezone.

# This script ensures that the timezone pattern in the specified Docker Compose files is replaced with the current server timezone.
