from prometheus_api_client import PrometheusConnect
from openstack import connection
import time
import os
from dotenv import load_dotenv, dotenv_values

load_dotenv()

# Cloud capacity
max_available_instances = 5
scale_up_threshold = 0.8
scale_down_threshold = 0.2

# OpenStack configuration
auth_url = 'https://cloud.cs.oslomet.no:5000/v3'
project_name = os.getenv("ALTO_PROJECT_NAME")
username = os.getenv("ALTO_USERNAME")
password = os.getenv("ALTO_PASSWORD")

# Prometheus configuration
prometheus_url = 'http://10.196.36.126:9090/'
query = 'sum(player_count) by (title)'
instance_capacity = 500000  # Adjust this value according to your setup
target_title = 'PLAYERUNKNOWNS BATTLEGROUNDS'  # Title you want to filter


# Initialize the connection to Prometheus
prom = PrometheusConnect(url=prometheus_url)

# Initialize the connection to OpenStack
conn = connection.Connection(auth_url=auth_url,
                             project_name=project_name,
                             username=username,
                             password=password,
                             project_domain_id='default',
                             user_domain_id='default')


def get_player_count():
    data = prom.custom_query(query)
    return data


def calculate_instances_and_player_count(player_data, title_to_filter):
    player_count = None
    instances_needed = None

    for entry in player_data:
        title = entry['metric']['title']
        if title == title_to_filter:
            player_count = int(entry['value'][1])
            # Calculate instances needed and round up to the nearest instance
            instances_needed = (
                player_count + instance_capacity - 1) // instance_capacity

    return player_count, instances_needed


def create_instance():
    # Define the instance details
    instance_name = 'new-instance'
    image_name = 'Ubuntu-22.04-LTS'  # Specify the image name, not the image_id
    flavor_name = 'C2R4_10G'
    network_name = 'acit'

    # Find the image and flavor
    image = conn.compute.find_image(image_name)  # Use image_name here
    flavor = conn.compute.find_flavor(flavor_name)

    # Find the network by name
    network = conn.network.find_network(network_name)

    # Create the instance and specify the network
    server = conn.compute.create_server(name=instance_name,
                                        image_id=image.id,
                                        flavor_id=flavor.id,
                                        networks=[{"uuid": network.id}])

    return server


def delete_instance(instance_id):
    # Delete the instance
    conn.compute.delete_server(instance_id, ignore_missing=False)


# Print instance capacity
print(f"Game tested for scaling :{target_title}")
# print("Max players played this game in last 30 days :{max_player_count}")
print(f"Max instances available on Cloud :{max_available_instances}")

if __name__ == '__main__':
    while True:
        # Get the player count from Prometheus
        player_data = get_player_count()
        player_count, instances_needed = calculate_instances_and_player_count(
            player_data, target_title)
        if player_count is not None:
            print(
                f'Title: {target_title}, Players: {player_count}, Instances Needed: {instances_needed}')
        else:
            print(f'Title: {target_title} not found in player_data.')

        # Get the current instances and their count
        existing_instances = list(conn.compute.servers())
        current_instance_count = len(existing_instances)
        print(f"Instances running Now :{current_instance_count}")

        # Calculate the total capacity and resources used
        total_capacity = current_instance_count * instance_capacity
        total_resources_used = player_count

        # Scale up: Create instances as needed
        while total_resources_used / total_capacity > scale_up_threshold:
            new_instance = create_instance()
            print(
                f"Usage more than 80%, Hence Created instance: {new_instance.name} ({new_instance.id})")
            current_instance_count += 1
            # Update total capacity after creating a new instance
            total_capacity = current_instance_count * instance_capacity

        # Scale down: Delete instances if too many
        for server in existing_instances:
            if server.name == 'new-instance':
                # Check if there are more instances than needed and
                # if resource usage is below the scale down threshold
                if current_instance_count > instances_needed and total_resources_used / total_capacity < scale_down_threshold:
                    delete_instance(server.id)
                    print(
                        f"Usage less than 20%, Hence Deleted instance: {server.name} ({server.id})")
                    current_instance_count -= 1

        # Wait for 5 minutes before checking again
        time.sleep(300)
