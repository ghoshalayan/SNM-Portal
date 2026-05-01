"""Add Country, StateMaster, DistrictMaster, DiaMaster tables

Revision ID: a1b2c3d4e5f6
Revises: f3a1b2c4d5e6
Create Date: 2026-03-29 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f3a1b2c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Country table
    op.create_table(
        'Country',
        sa.Column('countryid', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('countryname', sa.String(50), nullable=False),
        sa.Column('isActive', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('createdon', sa.DateTime(), nullable=True),
        sa.Column('createdby', sa.Integer(), nullable=True),
        sa.Column('lastupdateon', sa.DateTime(), nullable=True),
        sa.Column('lastupdateby', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('countryid'),
    )

    # StateMaster table
    op.create_table(
        'StateMaster',
        sa.Column('stateid', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('StateName', sa.String(50), nullable=False),
        sa.Column('Country', sa.String(50), nullable=True),
        sa.Column('isActive', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('createdon', sa.DateTime(), nullable=True),
        sa.Column('createdby', sa.Integer(), nullable=True),
        sa.Column('lastupdateon', sa.DateTime(), nullable=True),
        sa.Column('lastupdateby', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('stateid'),
    )

    # DistrictMaster table
    op.create_table(
        'DistrictMaster',
        sa.Column('districtid', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('districName', sa.String(50), nullable=False),
        sa.Column('StateName', sa.String(50), nullable=True),
        sa.Column('Country', sa.String(50), nullable=True),
        sa.Column('isActive', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('createdon', sa.DateTime(), nullable=True),
        sa.Column('createdby', sa.Integer(), nullable=True),
        sa.Column('lastupdateon', sa.DateTime(), nullable=True),
        sa.Column('lastupdateby', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('districtid'),
    )

    # DiaMaster table
    op.create_table(
        'DiaMaster',
        sa.Column('diaid', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('itemid', sa.Integer(), nullable=False),
        sa.Column('diadescription', sa.String(50), nullable=False),
        sa.Column('companyId', sa.Integer(), nullable=False),
        sa.Column('isActive', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('createdon', sa.DateTime(), nullable=True),
        sa.Column('createdby', sa.Integer(), nullable=True),
        sa.Column('lastupdateon', sa.DateTime(), nullable=True),
        sa.Column('lastupdateby', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['itemid'], ['ItemName.itemId']),
        sa.ForeignKeyConstraint(['companyId'], ['Company.companyId']),
        sa.PrimaryKeyConstraint('diaid'),
    )

    # Seed default Country: India
    op.execute("INSERT INTO Country (countryname, isActive) VALUES ('India', 1)")

    # Seed Indian states
    states = [
        'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
        'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand',
        'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur',
        'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab',
        'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
        'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
        'Andaman and Nicobar Islands', 'Chandigarh', 'Dadra and Nagar Haveli and Daman and Diu',
        'Delhi', 'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry',
    ]
    for s in states:
        op.execute(f"INSERT INTO StateMaster (StateName, Country, isActive) VALUES ('{s}', 'India', 1)")

    # Seed districts for major states
    districts = {
        'Maharashtra': [
            'Mumbai', 'Pune', 'Nagpur', 'Thane', 'Nashik', 'Aurangabad', 'Solapur',
            'Kolhapur', 'Sangli', 'Satara', 'Ratnagiri', 'Sindhudurg', 'Ahmednagar',
            'Jalgaon', 'Dhule', 'Nandurbar', 'Beed', 'Latur', 'Osmanabad', 'Nanded',
            'Parbhani', 'Hingoli', 'Jalna', 'Buldhana', 'Akola', 'Washim', 'Amravati',
            'Yavatmal', 'Wardha', 'Chandrapur', 'Bhandara', 'Gondia', 'Gadchiroli',
            'Raigad', 'Palghar',
        ],
        'Gujarat': [
            'Ahmedabad', 'Surat', 'Vadodara', 'Rajkot', 'Bhavnagar', 'Jamnagar',
            'Junagadh', 'Gandhinagar', 'Kutch', 'Anand', 'Kheda', 'Panchmahal',
            'Dahod', 'Mahisagar', 'Sabarkantha', 'Aravalli', 'Banaskantha', 'Patan',
            'Mehsana', 'Surendranagar', 'Morbi', 'Devbhumi Dwarka', 'Porbandar',
            'Gir Somnath', 'Amreli', 'Botad', 'Bharuch', 'Narmada', 'Tapi',
            'Navsari', 'Valsad', 'Dang', 'Chhota Udaipur',
        ],
        'Karnataka': [
            'Bangalore Urban', 'Bangalore Rural', 'Mysore', 'Belgaum', 'Hubli-Dharwad',
            'Mangalore', 'Gulbarga', 'Bellary', 'Bijapur', 'Shimoga', 'Tumkur',
            'Raichur', 'Hassan', 'Mandya', 'Chitradurga', 'Davangere', 'Udupi',
            'Chikmagalur', 'Kodagu', 'Bagalkot', 'Gadag', 'Haveri', 'Koppal',
            'Yadgir', 'Chamarajanagar', 'Ramanagara', 'Chikkaballapur',
        ],
        'Tamil Nadu': [
            'Chennai', 'Coimbatore', 'Madurai', 'Tiruchirappalli', 'Salem',
            'Tirunelveli', 'Erode', 'Vellore', 'Thoothukudi', 'Thanjavur',
            'Dindigul', 'Kanchipuram', 'Cuddalore', 'Nagapattinam', 'Villupuram',
            'Tiruvannamalai', 'Namakkal', 'Karur', 'Sivaganga', 'Virudhunagar',
            'Ramanathapuram', 'Theni', 'Tiruppur', 'Nilgiris', 'Dharmapuri',
            'Krishnagiri', 'Perambalur', 'Ariyalur', 'Pudukkottai',
        ],
        'Uttar Pradesh': [
            'Lucknow', 'Kanpur Nagar', 'Agra', 'Varanasi', 'Allahabad', 'Meerut',
            'Ghaziabad', 'Noida', 'Bareilly', 'Aligarh', 'Moradabad', 'Saharanpur',
            'Gorakhpur', 'Jhansi', 'Mathura', 'Firozabad', 'Muzaffarnagar',
            'Shahjahanpur', 'Rampur', 'Ayodhya', 'Sultanpur', 'Sitapur',
            'Hardoi', 'Unnao', 'Rae Bareli', 'Fatehpur', 'Pratapgarh',
            'Jaunpur', 'Mirzapur', 'Basti', 'Deoria',
        ],
        'Rajasthan': [
            'Jaipur', 'Jodhpur', 'Udaipur', 'Kota', 'Bikaner', 'Ajmer',
            'Bhilwara', 'Alwar', 'Sikar', 'Bharatpur', 'Pali', 'Sri Ganganagar',
            'Tonk', 'Barmer', 'Jaisalmer', 'Nagaur', 'Jhunjhunu', 'Churu',
            'Hanumangarh', 'Sawai Madhopur', 'Bundi', 'Jhalawar', 'Baran',
            'Chittorgarh', 'Pratapgarh', 'Dungarpur', 'Banswara', 'Rajsamand',
            'Karauli', 'Dausa', 'Dholpur',
        ],
        'West Bengal': [
            'Kolkata', 'Howrah', 'North 24 Parganas', 'South 24 Parganas', 'Hooghly',
            'Nadia', 'Murshidabad', 'Bardhaman', 'Birbhum', 'Bankura', 'Purulia',
            'Medinipur East', 'Medinipur West', 'Jalpaiguri', 'Darjeeling',
            'Cooch Behar', 'Malda', 'Dinajpur Uttar', 'Dinajpur Dakshin',
        ],
        'Delhi': [
            'Central Delhi', 'East Delhi', 'New Delhi', 'North Delhi', 'North East Delhi',
            'North West Delhi', 'Shahdara', 'South Delhi', 'South East Delhi',
            'South West Delhi', 'West Delhi',
        ],
        'Telangana': [
            'Hyderabad', 'Rangareddy', 'Medchal-Malkajgiri', 'Sangareddy', 'Nalgonda',
            'Warangal Urban', 'Warangal Rural', 'Karimnagar', 'Khammam', 'Nizamabad',
            'Adilabad', 'Mahabubnagar', 'Siddipet', 'Medak', 'Jagtial', 'Peddapalli',
        ],
        'Andhra Pradesh': [
            'Visakhapatnam', 'Vijayawada', 'Guntur', 'Nellore', 'Kurnool', 'Tirupati',
            'Kakinada', 'Rajahmundry', 'Kadapa', 'Anantapur', 'Eluru', 'Ongole',
            'Srikakulam', 'Vizianagaram', 'Chittoor', 'Prakasam', 'Krishna',
            'West Godavari', 'East Godavari',
        ],
        'Kerala': [
            'Thiruvananthapuram', 'Kochi', 'Kozhikode', 'Thrissur', 'Kollam',
            'Palakkad', 'Alappuzha', 'Kannur', 'Kottayam', 'Malappuram',
            'Pathanamthitta', 'Idukki', 'Wayanad', 'Kasaragod',
        ],
        'Madhya Pradesh': [
            'Bhopal', 'Indore', 'Jabalpur', 'Gwalior', 'Ujjain', 'Sagar',
            'Dewas', 'Satna', 'Ratlam', 'Rewa', 'Singrauli', 'Burhanpur',
            'Khandwa', 'Morena', 'Bhind', 'Chhindwara', 'Shivpuri', 'Vidisha',
            'Damoh', 'Panna', 'Hoshangabad', 'Seoni', 'Betul',
        ],
        'Punjab': [
            'Ludhiana', 'Amritsar', 'Jalandhar', 'Patiala', 'Bathinda', 'Mohali',
            'Pathankot', 'Hoshiarpur', 'Kapurthala', 'Moga', 'Firozpur',
            'Faridkot', 'Muktsar', 'Mansa', 'Sangrur', 'Barnala', 'Gurdaspur',
            'Tarn Taran', 'Fatehgarh Sahib', 'Rupnagar', 'Nawanshahr',
        ],
        'Haryana': [
            'Gurgaon', 'Faridabad', 'Panipat', 'Ambala', 'Karnal', 'Hisar',
            'Rohtak', 'Sonipat', 'Yamunanagar', 'Panchkula', 'Bhiwani',
            'Sirsa', 'Jind', 'Rewari', 'Mahendragarh', 'Palwal', 'Kurukshetra',
            'Kaithal', 'Fatehabad', 'Nuh', 'Charkhi Dadri',
        ],
        'Bihar': [
            'Patna', 'Gaya', 'Bhagalpur', 'Muzaffarpur', 'Darbhanga', 'Purnia',
            'Ara', 'Begusarai', 'Katihar', 'Munger', 'Chapra', 'Samastipur',
            'Hajipur', 'Sasaram', 'Dehri', 'Siwan', 'Motihari', 'Nawada',
            'Buxar', 'Banka', 'Lakhisarai', 'Jamui', 'Jehanabad',
        ],
        'Jharkhand': [
            'Ranchi', 'Jamshedpur', 'Dhanbad', 'Bokaro', 'Deoghar', 'Hazaribagh',
            'Giridih', 'Ramgarh', 'Dumka', 'Chaibasa', 'Palamu', 'Gumla',
            'Lohardaga', 'Pakur', 'Godda', 'Sahebganj',
        ],
        'Odisha': [
            'Bhubaneswar', 'Cuttack', 'Rourkela', 'Berhampur', 'Sambalpur',
            'Puri', 'Balasore', 'Bhadrak', 'Baripada', 'Jharsuguda', 'Jeypore',
            'Angul', 'Dhenkanal', 'Kendujhar', 'Koraput', 'Rayagada',
        ],
        'Chhattisgarh': [
            'Raipur', 'Bhilai', 'Bilaspur', 'Korba', 'Durg', 'Rajnandgaon',
            'Jagdalpur', 'Ambikapur', 'Raigarh', 'Dhamtari', 'Mahasamund',
        ],
        'Assam': [
            'Guwahati', 'Silchar', 'Dibrugarh', 'Jorhat', 'Nagaon', 'Tinsukia',
            'Tezpur', 'Bongaigaon', 'Karimganj', 'North Lakhimpur',
        ],
        'Goa': ['North Goa', 'South Goa'],
        'Himachal Pradesh': [
            'Shimla', 'Mandi', 'Kangra', 'Solan', 'Kullu', 'Hamirpur', 'Una',
            'Bilaspur', 'Sirmaur', 'Chamba', 'Kinnaur', 'Lahaul and Spiti',
        ],
        'Uttarakhand': [
            'Dehradun', 'Haridwar', 'Nainital', 'Udham Singh Nagar', 'Almora',
            'Pauri Garhwal', 'Tehri Garhwal', 'Chamoli', 'Pithoragarh',
            'Rudraprayag', 'Champawat', 'Bageshwar', 'Uttarkashi',
        ],
    }
    for state, dists in districts.items():
        for d in dists:
            escaped_d = d.replace("'", "''")
            escaped_s = state.replace("'", "''")
            op.execute(
                f"INSERT INTO DistrictMaster (districName, StateName, Country, isActive) "
                f"VALUES ('{escaped_d}', '{escaped_s}', 'India', 1)"
            )


def downgrade() -> None:
    op.drop_table('DiaMaster')
    op.drop_table('DistrictMaster')
    op.drop_table('StateMaster')
    op.drop_table('Country')
